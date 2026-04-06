"""Implementation of [org_parser.document.Document][] — a full Org Mode document."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING, Any

from org_parser._node import is_error_node
from org_parser._nodes import (
    AUTHOR,
    CATEGORY,
    DESCRIPTION,
    DRAWER,
    FILETAGS,
    HEADING,
    LOGBOOK_DRAWER,
    PROPERTY_DRAWER,
    SPECIAL_KEYWORD,
    TITLE,
    TODO,
    ZEROTH_SECTION,
)
from org_parser.element import (
    Drawer,
    Logbook,
    Properties,
)
from org_parser.element._dirty_list import DirtyList
from org_parser.element._element import (
    Element,
    build_semantic_repr,
    coerce_element_body,
    element_from_error_or_unknown,
    ensure_trailing_newline,
)
from org_parser.element._keyword import Keyword
from org_parser.text._rich_text import RichText, coerce_optional_rich_text

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    import tree_sitter

    from org_parser.document._heading import Heading

__all__ = ["Document", "ParseError"]

# Canonical render order for dedicated keywords and the set for fast lookup.
_DEDICATED_ORDER = [TITLE, AUTHOR, CATEGORY, DESCRIPTION, TODO]
_DEDICATED_KEYS: frozenset[str] = frozenset(_DEDICATED_ORDER)


@dataclasses.dataclass(frozen=True, slots=True)
class ParseError:
    """A single parse error captured during semantic extraction.

    Attributes:
        start_point: ``(row, column)`` of the error node's start position.
        end_point: ``(row, column)`` of the error node's end position.
        text: The verbatim source text span covered by the error node.
        message: Semantic classification describing the parse error category.
        _node: The raw tree-sitter node (private; not part of public API).
    """

    start_point: tuple[int, int]
    end_point: tuple[int, int]
    text: str
    _node: tree_sitter.Node = dataclasses.field(repr=False, compare=False)
    message: str = "Unexpected parse node"


_ERROR_NODE_MESSAGE = "Encountered parser ERROR node"
_MISSING_NODE_MESSAGE_PREFIX = "Encountered parser MISSING node"
_FALLBACK_NODE_MESSAGE = "Unexpected parse node"
_DRAWER_MARKER_TRAILING_MESSAGE = "Trailing characters in drawer marker"
_INVALID_REPEAT_MESSAGE = "Invalid repeated-task entry"


def drawer_marker_trailing_message() -> str:
    """Return the canonical parse-error message for malformed drawer markers."""
    return _DRAWER_MARKER_TRAILING_MESSAGE


def invalid_repeat_message() -> str:
    """Return the canonical parse-error message for malformed repeat entries."""
    return _INVALID_REPEAT_MESSAGE


def _default_parse_error_message(node: tree_sitter.Node) -> str:
    """Return default semantic message for one parse-error *node*."""
    if node.type == "ERROR":
        return _ERROR_NODE_MESSAGE
    if node.is_missing:
        missing_token = node.type.strip()
        if missing_token == "":
            return _MISSING_NODE_MESSAGE_PREFIX
        return f"{_MISSING_NODE_MESSAGE_PREFIX}: {missing_token}"
    return _FALLBACK_NODE_MESSAGE


class Document:
    """Representation of a full Org Mode document.

    A [org_parser.document.Document][] exposes the zeroth-section body elements, top-level
    headings, and well-known keyword properties (``TITLE``, ``AUTHOR``,
    ``FILETAGS``, etc.) parsed from the file.

    Args:
        filename: The filename of the document.
        title: The value of the ``#+TITLE:`` keyword, or *None*.
        author: The value of the ``#+AUTHOR:`` keyword, or *None*.
        category: The value of the ``#+CATEGORY:`` keyword, or *None*.
        description: The value of the ``#+DESCRIPTION:`` keyword, or *None*.
        todo: The value of the ``#+TODO:`` keyword, or *None*.
        keywords: All special keywords as an ordered list of
            [org_parser.element.Keyword][] objects.  Keywords in this list that share a
            key with one of the dedicated parameters above will override the
            dedicated value (last-write-wins).
        properties: Merged zeroth-section ``PROPERTIES`` drawer, or *None*.
        logbook: Merged zeroth-section ``LOGBOOK`` drawer, or *None*.
        body: Zeroth-section elements (excluding headings and special
            keywords and dedicated drawers).
        children: Top-level headings.

    Example:
    ```python
    >>> from org_parser import loads
    >>> document = loads('''
    ... * TODO Heading 1
    ... ** TODO Heading 2
    ... *** TODO Heading 3
    ... ''')
    >>> document[0].title_text
    'Heading 1'
    >>> document[1].heading_text
    '** TODO Heading 2'
    ```
    """

    def __init__(
        self,
        *,
        filename: str,
        title: RichText | str | None = None,
        author: RichText | str | None = None,
        category: RichText | str | None = None,
        description: RichText | str | None = None,
        todo: RichText | str | None = None,
        keywords: Sequence[Keyword] = (),
        properties: Properties | None = None,
        logbook: Logbook | None = None,
        body: Sequence[Element] = (),
        children: Sequence[Heading] = (),
    ) -> None:
        self._filename = filename

        # Build the keyword list from dedicated params first, then merge
        # the explicit keywords list on top (last-write-wins).
        self._keywords: list[Keyword] = []
        self._init_set_keyword(TITLE, title)
        self._init_set_keyword(AUTHOR, author)
        self._init_set_keyword(CATEGORY, category)
        self._init_set_keyword(DESCRIPTION, description)
        self._init_set_keyword(TODO, todo)
        for kw in keywords:
            self._init_merge_keyword(kw)

        self._properties = properties if properties is not None else Properties()
        self._logbook = logbook if logbook is not None else Logbook()
        self._body: list[Element] = list(body)
        self._children: list[Heading] = list(children)
        self._node: tree_sitter.Node | None = None
        self._source: bytes | None = None
        self._dirty = False
        self._errors: list[ParseError] = []

        self._adopt_keywords(self._keywords)
        self._adopt_element(self._properties)
        self._adopt_element(self._logbook)
        self._adopt_elements(self._body)
        self._adopt_elements(self._children)

    # -- factory method ------------------------------------------------------

    @classmethod
    def from_source(cls, source: str, *, filename: str = "") -> Document:
        """Build a [org_parser.document.Document][] from Org source text.

        Args:
            source: Org source text to parse.
            filename: Optional filename assigned to the parsed document.

        Returns:
            A fully populated parse-backed [org_parser.document.Document][].

        Raises:
            ValueError: If the source contains parse errors.

        Example:
        ```python
        >>> from org_parser import Document
        >>> document = Document.from_source("* TODO Heading 1")
        >>> document.children[0].todo
        'TODO'
        ```
        """
        from org_parser._from_source import parse_document_from_source

        return parse_document_from_source(source, filename=filename)

    @classmethod
    def from_tree(
        cls,
        tree: tree_sitter.Tree,
        filename: str,
        source: bytes,
    ) -> Document:
        """Build a [org_parser.document.Document][] from a tree-sitter parse tree.

        Args:
            tree: The `tree_sitter.Tree` returned by the parser.
            filename: The filename of the source document.
            source: The raw source bytes that were parsed.

        Returns:
            A fully populated [org_parser.document.Document][] with headings built
            recursively.

        Example:
        ```python
        >>> from org_parser import Document
        >>> from org_parser._lang import PARSER
        >>> source = "* TODO Heading 1".encode()
        >>> tree = PARSER.parse(source)
        >>> document = Document.from_tree(tree, "notes.org", source)
        >>> document.children[0].todo
        'TODO'
        ```
        """
        # Lazy import to break the circular dependency with _heading.py.
        from org_parser.document._heading import Heading

        root = tree.root_node

        # --- create document shell ------------------------------------------
        doc = cls(filename=filename)
        doc._node = root
        doc._source = source

        # --- extract zeroth-section data ------------------------------------
        kw_list, properties, logbook, body = _parse_zeroth_section(root, parent=doc)
        doc._keywords = kw_list
        doc._properties = properties if properties is not None else Properties(parent=doc)
        doc._logbook = logbook if logbook is not None else Logbook(parent=doc)
        doc._body = body
        doc._adopt_keywords(doc._keywords)
        doc._adopt_element(doc._properties)
        doc._adopt_element(doc._logbook)
        doc._adopt_elements(doc._body)

        # --- build top-level headings ---------------------------------------
        for child in root.children:
            if child.type == HEADING:
                heading = Heading.from_node(
                    child,
                    document=doc,
                    parent=doc,
                )
                doc._children.append(heading)
            elif is_error_node(child):
                elem = element_from_error_or_unknown(child, doc, parent=doc)
                doc._body.append(elem)

        return doc

    # -- public read-only properties -----------------------------------------

    @property
    def filename(self) -> str:
        """The filename of the document file.

        Example:
        ```python
        >>> from org_parser import dump, loads
        >>> document = loads("* TODO Heading 1")
        >>> document.filename = "file.org"
        >>> dump(document)
        ```
        """
        return self._filename

    @filename.setter
    def filename(self, value: str) -> None:
        """Set the filename."""
        self._filename = value
        self.mark_dirty()

    @property
    def title(self) -> RichText | None:
        """The ``#+TITLE:`` value, or *None*.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> from org_parser import loads
        >>> document = loads("* TODO Heading 1")
        >>> document.title = RichText("Updated")
        >>> document
        #+TITLE: Updated
        * TODO Heading 1
        ```
        """
        kw = self._find_last_keyword(TITLE)
        return kw.value if kw is not None else None

    @title.setter
    def title(self, value: RichText | str | None) -> None:
        """Set the ``#+TITLE:`` value."""
        self._set_keyword_value(TITLE, value)

    @property
    def author(self) -> RichText | None:
        """The ``#+AUTHOR:`` value, or *None*.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> from org_parser import loads
        >>> document = loads("* TODO Heading 1")
        >>> document.children[0].todo
        'TODO'
        >>> document.author = RichText("Updated")
        >>> document.author.raw
        'Updated'
        ```
        """
        kw = self._find_last_keyword(AUTHOR)
        return kw.value if kw is not None else None

    @author.setter
    def author(self, value: RichText | str | None) -> None:
        """Set the ``#+AUTHOR:`` value."""
        self._set_keyword_value(AUTHOR, value)

    @property
    def category(self) -> RichText | None:
        """The effective category for this document.

        Returns the ``#+CATEGORY:`` keyword value when present.  Otherwise
        falls back to the stem of [org_parser.document.Document.filename][]
        (the basename without its file extension), which matches Org Mode's
        own default-category behaviour.  Returns *None* when no filename
        is known (empty string).

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> from org_parser import loads
        >>> document = loads("* TODO Heading 1")
        >>> document.children[0].category is None
        True
        >>> document.category = RichText("Updated")
        >>> document.children[0].category
        RichText("Updated")
        ```
        """
        kw = self._find_last_keyword(CATEGORY)
        if kw is not None:
            return kw.value
        stem = Path(self._filename).stem if self._filename else None
        return RichText(stem) if stem else None

    @category.setter
    def category(self, value: RichText | str | None) -> None:
        """Set the ``#+CATEGORY:`` value."""
        self._set_keyword_value(CATEGORY, value)

    @property
    def description(self) -> RichText | None:
        """The ``#+DESCRIPTION:`` value, or *None*."""
        kw = self._find_last_keyword(DESCRIPTION)
        return kw.value if kw is not None else None

    @description.setter
    def description(self, value: RichText | str | None) -> None:
        """Set the ``#+DESCRIPTION:`` value."""
        self._set_keyword_value(DESCRIPTION, value)

    @property
    def todo(self) -> RichText | None:
        """The ``#+TODO:`` value, or *None*.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> from org_parser import loads
        >>> document = loads("* TODO Heading 1")
        >>> document.todo = RichText("TODO WAITING | DONE")
        >>> document.todo_states
        ['TODO', ''WAITING']
        ```
        """
        kw = self._find_last_keyword(TODO)
        return kw.value if kw is not None else None

    @todo.setter
    def todo(self, value: RichText | str | None) -> None:
        """Set the ``#+TODO:`` value."""
        self._set_keyword_value(TODO, value)

    @property
    def tags(self) -> list[str]:
        """Tags from all ``#+FILETAGS:`` keywords, as individual strings.

        Returns an empty list when no ``#+FILETAGS:`` keyword is present.
        Multiple ``#+FILETAGS:`` lines are aggregated in keyword-list order.
        The returned list is a fresh copy; mutate via the setter.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> from org_parser import loads
        >>> document = loads("* TODO Heading 1")
        >>> document.children[0].tags
        []
        >>> document.tags = ["tag1", "tag2"]
        >>> document.children[0].tags
        ['tag1', 'tag2']
        ```
        """
        tags: list[str] = []
        for kw in self._keywords:
            if kw.key != FILETAGS:
                continue
            # Parse ":foo:bar:" → ["foo", "bar"], ignoring empty segments.
            tags.extend(t for t in str(kw.value).strip(":").split(":") if t)
        return tags

    @tags.setter
    def tags(self, value: list[str]) -> None:
        """Set document-level file tags, updating ``#+FILETAGS:`` accordingly.

        Setting an empty list removes the ``#+FILETAGS:`` keyword entirely.
        """
        had_filetags = any(kw.key == FILETAGS for kw in self._keywords)
        if not value:
            self._keywords = [kw for kw in self._keywords if kw.key != FILETAGS]
            if had_filetags:
                self.mark_dirty()
            return
        self._keywords = [kw for kw in self._keywords if kw.key != FILETAGS]
        filetags_str = ":" + ":".join(value) + ":"
        new_kw = Keyword(key=FILETAGS, value=RichText(filetags_str), parent=self)
        self._keywords.append(new_kw)
        self.mark_dirty()

    @property
    def keywords(self) -> list[Keyword]:
        """All special keywords as an ordered list.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads("#+OTHER: foo")
        >>> document.keywords
        [Keyword(key='OTHER', value=RichText('foo'))]
        >>> document.keywords = []
        >>> len(document.keywords)
        0
        ```
        """

        def on_keywords_mutation(wrapped: DirtyList[Keyword]) -> None:
            self._keywords = list(wrapped)
            self._adopt_keywords(self._keywords)
            self.mark_dirty()

        return DirtyList(self._keywords, on_mutation=on_keywords_mutation)

    @keywords.setter
    def keywords(self, value: list[Keyword]) -> None:
        """Set the keywords list."""
        self._keywords = list(value)
        self._adopt_keywords(self._keywords)
        self.mark_dirty()

    @property
    def properties(self) -> Properties:
        """Merged zeroth-section ``PROPERTIES`` drawer.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads("#+TITLE: Properties")
        >>> document.properties["key"] = RichText("Value")
        >>> print(str(document))
        #+TITLE: Properties
        :PROPERTIES:
        :key: Value
        :END:
        ```
        """
        return self._properties

    @properties.setter
    def properties(self, value: Properties | dict[str, Any] | None) -> None:
        """Set merged ``PROPERTIES`` drawer.

        Assigning ``None`` resets this to an empty drawer instance.
        """
        if value is None:
            properties = Properties(parent=self)
        elif isinstance(value, Properties):
            properties = value
        else:
            properties = Properties(properties=value, parent=self)
        self._properties = properties
        self._adopt_element(self._properties)
        self.mark_dirty()

    @property
    def logbook(self) -> Logbook:
        """Merged zeroth-section ``LOGBOOK`` drawer.

        Example:
        ```python
        >>> from org_parser.time import Clock
        >>> document = loads("#+TITLE: Logbook")
        >>> document.logbook.clock_entries = [Clock.from_source("CLOCK: [2025-10-10]")]
        >>> print(str(document))
        #+TITLE: Logbook
        :LOGBOOK:
        CLOCK: [2025-10-10]
        :END:
        ```
        """
        return self._logbook

    @logbook.setter
    def logbook(self, value: Logbook | None) -> None:
        """Set merged ``LOGBOOK`` drawer.

        Assigning ``None`` resets this to an empty drawer instance.
        """
        self._logbook = value if value is not None else Logbook(parent=self)
        self._adopt_element(self._logbook)
        self.mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Zeroth-section body elements (excludes keywords and headings).

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads("")
        >>> document.body = [Paragraph.from_source("Add some body text")]
        >>> print(str(document))
        Add some body text
        ```
        """

        def on_body_mutation(wrapped: DirtyList[Element]) -> None:
            self._body = list(wrapped)
            self._adopt_elements(self._body)
            self.mark_dirty()

        return DirtyList(self._body, on_mutation=on_body_mutation)

    @body.setter
    def body(self, value: Sequence[Element] | Element | str) -> None:
        """Set zeroth-section body elements."""
        self._body = list(coerce_element_body(value))
        self._adopt_elements(self._body)
        self.mark_dirty()

    @property
    def body_text(self) -> str:
        """Stringified text for all zeroth-section body elements."""
        return "".join(str(element) for element in self._body)

    @property
    def children(self) -> list[Heading]:
        """Top-level headings.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... * Heading 1
        ... ** Heading 2
        ... *** Heading 3
        ... ''')
        >>> document.children[0].children = document.children[0].children[0].children
        >>> print(document.render())
        * Heading 1
        *** Heading 3
        ```
        """

        def on_children_mutation(wrapped: DirtyList[Heading]) -> None:
            from org_parser.document._heading import ensure_child_heading_level

            self._children = list(wrapped)
            self._adopt_elements(self._children)
            for child in self._children:
                ensure_child_heading_level(child, parent_level=0)
            self.mark_dirty()

        return DirtyList(self._children, on_mutation=on_children_mutation)

    @children.setter
    def children(self, value: list[Heading]) -> None:
        """Set top-level headings and enforce minimum level.

        Each heading is adopted (parent set to this document) and then checked:
        if its [org_parser.document.Heading.level][] is zero or
        negative it is shifted — along with its entire descendant subtree — to
        level 1.  Only headings whose level is actually changed are marked
        dirty.
        """
        # Lazy import avoids the circular dependency with _heading.py.
        from org_parser.document._heading import ensure_child_heading_level

        self._children = list(value)
        self._adopt_elements(self._children)
        for child in self._children:
            ensure_child_heading_level(child, parent_level=0)
        self.mark_dirty()

    @property
    def all_headings(self) -> list[Heading]:
        """All headings in file-definition order across the full document tree.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... * Heading 1
        ... ** Heading 2
        ... ''')
        >>> len(document.all_headings)
        2
        >>> len(document[:])
        2
        ```
        """
        ordered: list[Heading] = []
        _collect_heading_subtree(self._children, ordered)
        return ordered

    @property
    def is_root(self) -> bool:
        """Whether this node is the root of a parsed document tree.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads("* TODO Heading 1")
        >>> document.is_root
        True
        ```
        """
        return True

    @property
    def is_leaf(self) -> bool:
        """Whether this document has no top-level headings.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads("* TODO Heading 1")
        >>> document.is_leaf
        False
        >>> document = loads("No headings")
        >>> document.is_leaf
        True
        ```
        """
        return not self._children

    @property
    def all_states(self) -> list[str]:
        """All discovered TODO keyword states from the ``#+TODO:`` definition.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads("#+TODO: TODO WAITING | DONE CANCELLED")
        >>> document.all_states
        ['TODO', 'WAITING', 'DONE', 'CANCELLED']
        ```
        """
        return _parse_todo_states(self._todo_keyword_values())[0]

    @property
    def todo_states(self) -> list[str]:
        """Discovered non-completed TODO states from the ``#+TODO:`` definition.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads("#+TODO: TODO WAITING | DONE CANCELLED")
        >>> document.todo_states
        ['TODO', 'WAITING']
        ```
        """
        return _parse_todo_states(self._todo_keyword_values())[1]

    @property
    def done_states(self) -> list[str]:
        """Discovered completed TODO states from the ``#+TODO:`` definition.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads("#+TODO: TODO WAITING | DONE CANCELLED")
        >>> document.todo_states
        ['DONE', 'CANCELLED']
        ```
        """
        return _parse_todo_states(self._todo_keyword_values())[2]

    def source_for(self, node: tree_sitter.Node) -> bytes:
        """Return source bytes for one node span.

        Args:
            node: Tree-sitter node to slice against.

        Returns:
            The source bytes covered by ``node.start_byte:node.end_byte``.

        Raises:
            ValueError: If this document has no source bytes.
        """
        if self._source is None:
            raise ValueError("Cannot slice source without document source bytes")
        return self._source[node.start_byte : node.end_byte]

    @property
    def dirty(self) -> bool:
        """Whether this document has been mutated after creation."""
        return self._dirty

    @property
    def errors(self) -> list[ParseError]:
        """Parse errors captured during [org_parser.document.Document.from_tree][] construction.

        Returns an empty list for programmatically constructed documents.
        The list is read-only: do not mutate it directly.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... * Heading
        ... SCHEDULED: yesterday
        ... ''')
        >>> document.errors
        [ParseError(
            start_point=Point(row=2, column=0),
            end_point=Point(row=2, column=20),
            text='SCHEDULED: yesterday',
            message='Encountered parser ERROR node'
        )]
        ```
        """
        return self._errors

    def report_error(self, node: tree_sitter.Node, message: str | None = None) -> None:
        """Record a parse error for *node*.

        Extracts the verbatim source text for the node and appends a
        [org_parser.document.ParseError][] to the internal errors list.

        Args:
            node: The tree-sitter ``ERROR`` or missing node to record.
            message: Optional semantic classification. When omitted, a
                default category is inferred from ``node``.

        Raises:
            ValueError: If this document has no source bytes.
        """
        self._errors.append(
            ParseError(
                start_point=node.start_point,
                end_point=node.end_point,
                text=self.source_for(node).decode(),
                _node=node,
                message=message if message is not None else _default_parse_error_message(node),
            )
        )

    def mark_dirty(self) -> None:
        """Mark this document as dirty.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... Some text.
        ... #+TITLE: Title
        ... More text
        ... ''')
        >>> document.mark_dirty()
        >>> document.dirty
        True
        >>> print(str(document))
        #+TITLE: Title

        Some text.
        More text
        ```
        """
        if self._dirty:
            return
        self._dirty = True

    def reformat(self) -> None:
        """Reformat the entire document.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... * Heading 1
        ... ** Heading 2
        ... CLOSED: <2025-10-10>
        ... SCHEDULED: <2025-10-10>
        ... ''')
        >>> document.reformat()
        >>> print(document.render())
        * Heading 1
        ** Heading 2
        SCHEDULED: <2025-10-10> CLOSED: <2025-10-10>
        ```
        """
        for keyword in self._keywords:
            keyword.reformat()
        self._properties.reformat()
        self._logbook.reformat()
        for element in self._body:
            element.reformat()
        for child in self._children:
            child.reformat()
        self.mark_dirty()

    def _find_last_keyword(self, key: str) -> Keyword | None:
        """Return the last keyword with *key*, or *None* when absent."""
        for kw in reversed(self._keywords):
            if kw.key == key:
                return kw
        return None

    def _todo_keyword_values(self) -> list[RichText]:
        """Return ``#+TODO:`` keyword values in document order."""
        return [kw.value for kw in self._keywords if kw.key == TODO]

    def _set_keyword_value(self, key: str, value: RichText | str | None) -> None:
        """Update, create, or remove a keyword entry by key.

        If *value* is *None* the keyword is removed from the list.  Otherwise
        the existing keyword's value is updated in place, or a new keyword is
        appended when no entry for *key* exists.
        """
        coerced = coerce_optional_rich_text(value)
        existing = self._find_last_keyword(key)
        if coerced is None:
            self._keywords = [kw for kw in self._keywords if kw.key != key]
        elif existing is not None:
            existing.value = coerced
        else:
            new_kw = Keyword(key=key, value=coerced, parent=self)
            self._keywords.append(new_kw)
        self.mark_dirty()

    def _init_set_keyword(self, key: str, value: RichText | str | None) -> None:
        """Init-time helper: append a keyword for *key* if *value* is not *None*."""
        coerced = coerce_optional_rich_text(value)
        if coerced is None:
            return
        self._keywords.append(Keyword(key=key, value=coerced))

    def _init_merge_keyword(self, kw: Keyword) -> None:
        """Init-time helper: merge *kw* into the list (last-write-wins).

        If a keyword with the same key already exists it is replaced in place;
        otherwise *kw* is appended.
        """
        for i, existing in enumerate(self._keywords):
            if existing.key == kw.key:
                self._keywords[i] = kw
                return
        self._keywords.append(kw)

    def _adopt_element(
        self,
        value: Keyword | Properties | Logbook | Element | Heading | None,
    ) -> None:
        """Assign this document as parent for one child semantic object."""
        if value is None:
            return
        value.parent = self

    def _adopt_keywords(self, keywords: list[Keyword]) -> None:
        """Assign this document as parent for all keyword entries."""
        for kw in keywords:
            self._adopt_element(kw)

    def _adopt_elements(
        self,
        values: Sequence[Keyword | Properties | Logbook | Element | Heading | None],
    ) -> None:
        """Assign this document as parent for each provided child object."""
        for value in values:
            self._adopt_element(value)

    def render(self) -> str:
        """Return the complete Org Mode text for a document including headings.

        For clean (unmodified) parse-backed documents the original source bytes are
        returned verbatim, preserving all whitespace and formatting. For dirty
        documents, or documents built without a backing source, the zeroth section
        and every heading subtree are reconstructed from their semantic fields via
        :func:`str`.

        Returns:
            Full Org Mode text including all headings.
        """
        if not self.dirty and self._node is not None:
            return self.source_for(self._node).decode()
        parts: list[str] = [str(self)]
        parts.extend(heading.render() for heading in self.children)
        return "".join(parts)

    # -- dunder protocols ----------------------------------------------------

    def __str__(self) -> str:
        """Return a textual representation of the document zeroth section.

        When the document is clean and still backed by a parse tree, this
        returns the exact source slice for the zeroth section to preserve
        original whitespace and formatting. Once the document is dirty, this
        falls back to a reconstructed representation from semantic fields.
        """
        if not self._dirty and self._node is not None:
            zeroth = _find_first_child_by_type(self._node, ZEROTH_SECTION)
            if zeroth is None:
                return ""
            return self.source_for(zeroth).decode()

        return _render_document_dirty(self)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        extra_kws = [kw for kw in self._keywords if kw.key not in _DEDICATED_KEYS]
        title = self.title
        author = self.author
        category = self.category
        description = self.description
        todo = self.todo
        properties = self._properties if _has_non_empty_properties(self._properties) else None
        logbook = self._logbook if _has_non_empty_logbook(self._logbook) else None
        return build_semantic_repr(
            "Document",
            filename=self._filename,
            title=title,
            author=author,
            category=category,
            description=description,
            todo=todo,
            keywords=extra_kws,
            properties=properties,
            logbook=logbook,
            body=self._body,
            children=self._children,
        )

    def __iter__(self) -> Iterator[Heading]:
        """Iterate over all headings in file-definition order."""
        return iter(self.all_headings)

    def __len__(self) -> int:
        """Return number of headings across the full document tree."""
        return len(self.all_headings)

    def __getitem__(self, index: int | slice) -> Heading | list[Heading]:
        """Return one (or slice) of headings from the document, including subheadings."""
        return self.all_headings[index]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_zeroth_section(
    root: tree_sitter.Node,
    *,
    parent: Document,
) -> tuple[list[Keyword], Properties | None, Logbook | None, list[Element]]:
    """Extract all keywords and body elements from the zeroth section.

    Returns:
        A ``(keywords, properties, logbook, body)`` tuple. *keywords* is an
        ordered list of [org_parser.element.Keyword][] values in source order; duplicate
        keys are preserved.  Dedicated drawer values are merged across
        repeated drawers. *body* contains non-keyword,
        non-dedicated-drawer elements.
    """
    from org_parser.document._body import (
        extract_body_element,
        merge_logbook_drawers,
        merge_properties_drawers,
    )
    from org_parser.element._structure_recovery import (
        attach_affiliated_keywords,
    )

    keywords: list[Keyword] = []
    property_drawers: list[Properties] = []
    logbook_drawers: list[Logbook] = []
    body: list[Element] = []

    for child in root.children:
        if child.type == ZEROTH_SECTION:
            for sc in child.named_children:
                if sc.type == SPECIAL_KEYWORD:
                    keywords.append(_extract_keyword(sc, parent=parent))
                elif sc.type == PROPERTY_DRAWER:
                    property_drawers.append(Properties.from_node(sc, parent, parent=parent))
                elif sc.type == LOGBOOK_DRAWER:
                    logbook_drawers.append(Logbook.from_node(sc, parent, parent=parent))
                elif sc.type == DRAWER:
                    body.append(Drawer.from_node(sc, parent, parent=parent))
                else:
                    body.append(extract_body_element(sc, parent=parent, document=parent))
            break  # only one zeroth section

    attach_affiliated_keywords(body)
    return (
        keywords,
        merge_properties_drawers(property_drawers, parent=parent),
        merge_logbook_drawers(logbook_drawers, parent=parent),
        body,
    )


def _extract_keyword(
    kw_node: tree_sitter.Node,
    *,
    parent: Document,
) -> Keyword:
    """Build and return a [org_parser.element.Keyword][] for a single ``special_keyword`` node."""
    return Keyword.from_node(kw_node, parent, parent=parent)


def _find_first_child_by_type(
    node: tree_sitter.Node,
    node_type: str,
) -> tree_sitter.Node | None:
    """Return the first direct child with the given type, if any."""
    for child in node.children:
        if child.type == node_type:
            return child
    return None


def _append_heading_subtree(headings: Sequence[Heading], parts: list[str]) -> None:
    """Recursively append each heading and its sub-headings to *parts*.

    Args:
        headings: Sequence of sibling headings to serialize.
        parts: Accumulator list that string fragments are appended to.
    """
    for heading in headings:
        parts.append(str(heading))
        _append_heading_subtree(heading.children, parts)


def _collect_heading_subtree(headings: Sequence[Heading], out: list[Heading]) -> None:
    """Append *headings* and descendants to *out* in source definition order."""
    for heading in headings:
        out.append(heading)
        _collect_heading_subtree(heading.children, out)


def _parse_todo_states(
    todo_values: Sequence[RichText],
) -> tuple[list[str], list[str], list[str]]:
    """Return ``(all_states, todo_states, done_states)`` for ``#+TODO:`` values."""
    todo_states: list[str] = []
    done_states: list[str] = []

    for todo in todo_values:
        in_done_group = False
        for state_part in str(todo).split():
            if state_part == "|":
                in_done_group = True
                continue

            state = _todo_state_name(state_part)
            if state is None:
                continue
            if in_done_group:
                if state not in done_states:
                    done_states.append(state)
            elif state not in todo_states:
                todo_states.append(state)

    all_states = [*todo_states]
    for state in done_states:
        if state not in all_states:
            all_states.append(state)
    return all_states, todo_states, done_states


def _todo_state_name(state_part: str) -> str | None:
    """Extract one TODO state token name from keyword syntax.

    This strips optional fast-selection metadata, for example:
    ``TODO(t)`` -> ``TODO`` and ``DONE(d@/!)`` -> ``DONE``.
    """
    stripped = state_part.strip()
    if stripped == "":
        return None
    head, _, _ = stripped.partition("(")
    return head if head != "" else None


def _render_document_dirty(document: Document) -> str:
    """Render a dirty document from semantic fields only."""
    parts: list[str] = []
    keywords = document.keywords

    # Render dedicated keywords in the canonical fixed order.
    for key in _DEDICATED_ORDER:
        parts.extend(
            ensure_trailing_newline(str(keyword)) for keyword in keywords if keyword.key == key
        )

    # Render non-dedicated keywords in their list order.
    parts.extend(
        ensure_trailing_newline(str(keyword))
        for keyword in keywords
        if keyword.key not in _DEDICATED_KEYS
    )

    if _has_non_empty_properties(document.properties):
        parts.append(ensure_trailing_newline(str(document.properties)))
    if _has_non_empty_logbook(document.logbook):
        parts.append(ensure_trailing_newline(str(document.logbook)))

    parts.extend(ensure_trailing_newline(str(element)) for element in document.body)

    return "".join(parts)


def _has_non_empty_properties(properties: Properties) -> bool:
    """Return whether a properties drawer contains at least one key."""
    return len(properties) > 0


def _has_non_empty_logbook(logbook: Logbook) -> bool:
    """Return whether a logbook drawer contains at least one body element."""
    return len(logbook) > 0
