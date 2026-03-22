"""Implementation of :class:`Document` — a full Org Mode document."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import TYPE_CHECKING

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
from org_parser.element._element import (
    Element,
    element_from_error_or_unknown,
)
from org_parser.element._keyword import Keyword
from org_parser.text._rich_text import RichText

if TYPE_CHECKING:
    from collections.abc import Sequence

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
        _node: The raw tree-sitter node (private; not part of public API).
    """

    start_point: tuple[int, int]
    end_point: tuple[int, int]
    text: str
    _node: tree_sitter.Node = dataclasses.field(repr=False, compare=False)


class Document:
    """Representation of a full Org Mode document.

    A :class:`Document` exposes the zeroth-section body elements, top-level
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
            :class:`Keyword` objects.  Keywords in this list that share a
            key with one of the dedicated parameters above will override the
            dedicated value (last-write-wins).
        properties: Merged zeroth-section ``PROPERTIES`` drawer, or *None*.
        logbook: Merged zeroth-section ``LOGBOOK`` drawer, or *None*.
        body: Zeroth-section elements (excluding headings and special
            keywords and dedicated drawers).
        children: Top-level headings.
    """

    def __init__(
        self,
        *,
        filename: str,
        title: RichText | None = None,
        author: RichText | None = None,
        category: RichText | None = None,
        description: RichText | None = None,
        todo: RichText | None = None,
        keywords: list[Keyword] | None = None,
        properties: Properties | None = None,
        logbook: Logbook | None = None,
        body: list[Element] | None = None,
        children: list[Heading] | None = None,
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
        if keywords is not None:
            for kw in keywords:
                self._init_merge_keyword(kw)

        self._properties = properties
        self._logbook = logbook
        self._body: list[Element] = body if body is not None else []
        self._children: list[Heading] = children if children is not None else []
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
    def from_tree(
        cls,
        tree: tree_sitter.Tree,
        filename: str,
        source: bytes,
    ) -> Document:
        """Build a :class:`Document` from a tree-sitter parse tree.

        Args:
            tree: The :class:`~tree_sitter.Tree` returned by the parser.
            filename: The filename of the source document.
            source: The raw source bytes that were parsed.

        Returns:
            A fully populated :class:`Document` with headings built
            recursively.
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
        doc._properties = properties
        doc._logbook = logbook
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
        """The filename of the document file."""
        return self._filename

    @filename.setter
    def filename(self, value: str) -> None:
        """Set the filename and mark the document as dirty."""
        self._filename = value
        self._mark_dirty()

    @property
    def title(self) -> RichText | None:
        """The ``#+TITLE:`` value, or *None*."""
        kw = self._find_keyword(TITLE)
        return kw.value if kw is not None else None

    @title.setter
    def title(self, value: RichText | None) -> None:
        """Set the ``#+TITLE:`` value and mark the document as dirty."""
        self._set_keyword_value(TITLE, value)

    @property
    def author(self) -> RichText | None:
        """The ``#+AUTHOR:`` value, or *None*."""
        kw = self._find_keyword(AUTHOR)
        return kw.value if kw is not None else None

    @author.setter
    def author(self, value: RichText | None) -> None:
        """Set the ``#+AUTHOR:`` value and mark the document as dirty."""
        self._set_keyword_value(AUTHOR, value)

    @property
    def category(self) -> RichText | None:
        """The effective category for this document.

        Returns the ``#+CATEGORY:`` keyword value when present.  Otherwise
        falls back to the stem of :attr:`filename` (the basename without its
        file extension), which matches Org Mode's own default-category
        behaviour.  Returns *None* when no filename is known (empty string).
        """
        kw = self._find_keyword(CATEGORY)
        if kw is not None:
            return kw.value
        stem = Path(self._filename).stem if self._filename else None
        return RichText(stem) if stem else None

    @category.setter
    def category(self, value: RichText | None) -> None:
        """Set the ``#+CATEGORY:`` value and mark the document as dirty."""
        self._set_keyword_value(CATEGORY, value)

    @property
    def description(self) -> RichText | None:
        """The ``#+DESCRIPTION:`` value, or *None*."""
        kw = self._find_keyword(DESCRIPTION)
        return kw.value if kw is not None else None

    @description.setter
    def description(self, value: RichText | None) -> None:
        """Set the ``#+DESCRIPTION:`` value and mark the document as dirty."""
        self._set_keyword_value(DESCRIPTION, value)

    @property
    def todo(self) -> RichText | None:
        """The ``#+TODO:`` value, or *None*."""
        kw = self._find_keyword(TODO)
        return kw.value if kw is not None else None

    @todo.setter
    def todo(self, value: RichText | None) -> None:
        """Set the ``#+TODO:`` value and mark the document as dirty."""
        self._set_keyword_value(TODO, value)

    @property
    def tags(self) -> list[str]:
        """Tags from the ``#+FILETAGS:`` keyword, as individual strings.

        Returns an empty list when no ``#+FILETAGS:`` keyword is present.
        The returned list is a fresh copy; mutate via the setter.
        """
        kw = self._find_keyword(FILETAGS)
        if kw is None:
            return []
        # Parse ":foo:bar:" → ["foo", "bar"], ignoring empty segments.
        return [t for t in str(kw.value).strip(":").split(":") if t]

    @tags.setter
    def tags(self, value: list[str]) -> None:
        """Set document-level file tags, updating ``#+FILETAGS:`` accordingly.

        Setting an empty list removes the ``#+FILETAGS:`` keyword entirely.
        """
        if not value:
            kw = self._find_keyword(FILETAGS)
            if kw is not None:
                self._keywords.remove(kw)
            self._mark_dirty()
            return
        filetags_str = ":" + ":".join(value) + ":"
        existing = self._find_keyword(FILETAGS)
        if existing is not None:
            existing.value = RichText(filetags_str)
        else:
            new_kw = Keyword(key=FILETAGS, value=RichText(filetags_str), parent=self)
            self._keywords.append(new_kw)
        self._mark_dirty()

    @property
    def keywords(self) -> list[Keyword]:
        """All special keywords as an ordered list."""
        return self._keywords

    @keywords.setter
    def keywords(self, value: list[Keyword]) -> None:
        """Set the keywords list and mark the document as dirty."""
        self._keywords = value
        self._adopt_keywords(self._keywords)
        self._mark_dirty()

    @property
    def properties(self) -> Properties | None:
        """Merged zeroth-section ``PROPERTIES`` drawer, or *None*."""
        return self._properties

    @properties.setter
    def properties(self, value: Properties | None) -> None:
        """Set merged ``PROPERTIES`` drawer and mark the document dirty."""
        self._properties = value
        self._adopt_element(self._properties)
        self._mark_dirty()

    @property
    def logbook(self) -> Logbook | None:
        """Merged zeroth-section ``LOGBOOK`` drawer, or *None*."""
        return self._logbook

    @logbook.setter
    def logbook(self, value: Logbook | None) -> None:
        """Set merged ``LOGBOOK`` drawer and mark the document dirty."""
        self._logbook = value
        self._adopt_element(self._logbook)
        self._mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Zeroth-section body elements (excludes keywords and headings)."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set zeroth-section body elements and mark the document as dirty."""
        self._body = value
        self._adopt_elements(self._body)
        self._mark_dirty()

    @property
    def children(self) -> list[Heading]:
        """Top-level headings."""
        return self._children

    @children.setter
    def children(self, value: list[Heading]) -> None:
        """Set top-level headings, enforce minimum level, and mark dirty.

        Each heading is adopted (parent set to this document) and then checked:
        if its :attr:`~org_parser.document._heading.Heading.level` is zero or
        negative it is shifted — along with its entire descendant subtree — to
        level 1.  Only headings whose level is actually changed are marked
        dirty.
        """
        # Lazy import avoids the circular dependency with _heading.py.
        from org_parser.document._heading import ensure_child_heading_level

        self._children = value
        self._adopt_elements(self._children)
        for child in self._children:
            ensure_child_heading_level(child, parent_level=0)
        self._mark_dirty()

    @property
    def is_root(self) -> bool:
        """Whether this node is the root of a parsed document tree."""
        return True

    @property
    def is_leaf(self) -> bool:
        """Whether this document has no top-level headings."""
        return not self._children

    @property
    def all_states(self) -> list[str]:
        """All discovered TODO keyword states from the ``#+TODO:`` definition."""
        return _parse_todo_states(self._todo_keyword_values())[0]

    @property
    def todo_states(self) -> list[str]:
        """Discovered non-completed TODO states from the ``#+TODO:`` definition."""
        return _parse_todo_states(self._todo_keyword_values())[1]

    @property
    def done_states(self) -> list[str]:
        """Discovered completed TODO states from the ``#+TODO:`` definition."""
        return _parse_todo_states(self._todo_keyword_values())[2]

    @property
    def body_text(self) -> str:
        """Stringified text for all zeroth-section body elements."""
        return "".join(str(element) for element in self._body)

    @property
    def all_headings(self) -> list[Heading]:
        """All headings in file-definition order across the full document tree."""
        ordered: list[Heading] = []
        _collect_heading_subtree(self._children, ordered)
        return ordered

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
        """Parse errors captured during :meth:`from_tree` construction.

        Returns an empty list for programmatically constructed documents.
        The list is read-only: do not mutate it directly.
        """
        return self._errors

    def report_error(self, node: tree_sitter.Node) -> None:
        """Record a parse error for *node*.

        Extracts the verbatim source text for the node and appends a
        :class:`ParseError` to the internal errors list.

        Args:
            node: The tree-sitter ``ERROR`` or missing node to record.

        Raises:
            ValueError: If this document has no source bytes.
        """
        self._errors.append(
            ParseError(
                start_point=node.start_point,
                end_point=node.end_point,
                text=self.source_for(node).decode(),
                _node=node,
            )
        )

    def _mark_dirty(self) -> None:
        """Mark this document as dirty."""
        if self._dirty:
            return
        self._dirty = True

    def mark_dirty(self) -> None:
        """Mark this document as dirty.

        This public helper is intended for nested objects that need to bubble
        mutation state up to the owning document.
        """
        self._mark_dirty()

    def reformat(self) -> None:
        """Recursively mark document descendants dirty, then self dirty."""
        for keyword in self._keywords:
            keyword.reformat()
        if self._properties is not None:
            self._properties.reformat()
        if self._logbook is not None:
            self._logbook.reformat()
        for element in self._body:
            element.reformat()
        for child in self._children:
            child.reformat()
        self.mark_dirty()

    def _find_keyword(self, key: str) -> Keyword | None:
        """Return the first keyword with the given upper-cased key, or *None*."""
        for kw in self._keywords:
            if kw.key == key:
                return kw
        return None

    def _todo_keyword_values(self) -> list[RichText]:
        """Return ``#+TODO:`` keyword values in document order."""
        return [kw.value for kw in self._keywords if kw.key == TODO]

    def _set_keyword_value(self, key: str, value: RichText | None) -> None:
        """Update, create, or remove a keyword entry by key.

        If *value* is *None* the keyword is removed from the list.  Otherwise
        the existing keyword's value is updated in place, or a new keyword is
        appended when no entry for *key* exists.
        """
        existing = self._find_keyword(key)
        if value is None:
            if existing is not None:
                self._keywords.remove(existing)
        elif existing is not None:
            existing.value = value
        else:
            new_kw = Keyword(key=key, value=value, parent=self)
            self._keywords.append(new_kw)
        self._mark_dirty()

    def _init_set_keyword(self, key: str, value: RichText | None) -> None:
        """Init-time helper: append a keyword for *key* if *value* is not *None*."""
        if value is None:
            return
        self._keywords.append(Keyword(key=key, value=value))

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
        returned verbatim, preserving all whitespace and formatting.  For dirty
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
        parts = [f"filename={self._filename!r}"]
        title = self.title
        if title is not None:
            parts.append(f"title={title!r}")
        author = self.author
        if author is not None:
            parts.append(f"author={author!r}")
        category = self.category
        if category is not None:
            parts.append(f"category={category!r}")
        description = self.description
        if description is not None:
            parts.append(f"description={description!r}")
        todo = self.todo
        if todo is not None:
            parts.append(f"todo={todo!r}")
        extra_kws = [kw for kw in self._keywords if kw.key not in _DEDICATED_KEYS]
        if extra_kws:
            parts.append(f"keywords={extra_kws!r}")
        if self._properties is not None:
            parts.append(f"properties={self._properties!r}")
        if self._logbook is not None:
            parts.append(f"logbook={self._logbook!r}")
        if self._body:
            parts.append(f"body={self._body!r}")
        if self._children:
            parts.append(f"children={self._children!r}")
        return f"Document({', '.join(parts)})"


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
        ordered list of :class:`Keyword` values in source order; duplicate
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
        recover_lists,
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
                    property_drawers.append(
                        Properties.from_node(sc, parent, parent=parent)
                    )
                elif sc.type == LOGBOOK_DRAWER:
                    logbook_drawers.append(Logbook.from_node(sc, parent, parent=parent))
                elif sc.type == DRAWER:
                    body.append(Drawer.from_node(sc, parent, parent=parent))
                else:
                    body.append(
                        extract_body_element(sc, parent=parent, document=parent)
                    )
            break  # only one zeroth section

    recovered_body = recover_lists(body, parent=parent)
    attach_affiliated_keywords(recovered_body)
    return (
        keywords,
        merge_properties_drawers(property_drawers, parent=parent),
        merge_logbook_drawers(logbook_drawers, parent=parent),
        recovered_body,
    )


def _extract_keyword(
    kw_node: tree_sitter.Node,
    *,
    parent: Document,
) -> Keyword:
    """Build and return a :class:`Keyword` for a single ``special_keyword`` node."""
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
        for token in str(todo).split():
            if token == "|":
                in_done_group = True
                continue

            state = _todo_state_name(token)
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


def _todo_state_name(token: str) -> str | None:
    """Extract one TODO state token name from keyword syntax.

    This strips optional fast-selection metadata, for example:
    ``TODO(t)`` -> ``TODO`` and ``DONE(d@/!)`` -> ``DONE``.
    """
    stripped = token.strip()
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
        for kw in keywords:
            if kw.key == key:
                parts.append(str(kw))
                break

    # Render non-dedicated keywords in their list order.
    parts.extend(str(kw) for kw in keywords if kw.key not in _DEDICATED_KEYS)

    if document.properties is not None:
        parts.append(str(document.properties))
    if document.logbook is not None:
        parts.append(str(document.logbook))

    parts.extend(str(element) for element in document.body)

    return "".join(parts)
