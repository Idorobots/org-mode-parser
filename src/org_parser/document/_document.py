"""Implementation of :class:`Document` — a full Org Mode document."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

from org_parser.element import (
    Drawer,
    Logbook,
    Properties,
)
from org_parser.element._element import Element, reformat_value
from org_parser.element._keyword import Keyword

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._heading import Heading

__all__ = ["Document", "ParseError"]

# Node type names produced by the tree-sitter grammar.
_ZEROTH_SECTION = "zeroth_section"
_HEADING = "heading"
_SPECIAL_KEYWORD = "special_keyword"
_PROPERTY_DRAWER = "property_drawer"
_LOGBOOK_DRAWER = "logbook_drawer"
_DRAWER = "drawer"
_TITLE = "TITLE"
_AUTHOR = "AUTHOR"
_CATEGORY = "CATEGORY"
_DESCRIPTION = "DESCRIPTION"
_TODO = "TODO"


@dataclasses.dataclass(frozen=True, slots=True)
class ParseError:
    """A single parse error captured during semantic extraction.

    Attributes:
        node: The tree-sitter ``ERROR`` or missing node.
        text: The verbatim source text span covered by the error node.
    """

    node: tree_sitter.Node
    text: str


class Document:
    """Representation of a full Org Mode document.

    A :class:`Document` exposes the zeroth-section body elements, top-level
    headings, and well-known keyword properties (``TITLE``, ``AUTHOR``, etc.)
    parsed from the file.

    Args:
        filename: The filename of the document.
        title: The ``#+TITLE:`` keyword object, or *None*.
        author: The ``#+AUTHOR:`` keyword object, or *None*.
        category: The ``#+CATEGORY:`` keyword object, or *None*.
        description: The ``#+DESCRIPTION:`` keyword object, or *None*.
        todo: The ``#+TODO:`` keyword object, or *None*.
        keywords: Remaining special keywords not covered by the dedicated
            properties, keyed by upper-cased keyword name as :class:`Keyword`.
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
        title: Keyword | None = None,
        author: Keyword | None = None,
        category: Keyword | None = None,
        description: Keyword | None = None,
        todo: Keyword | None = None,
        keywords: dict[str, Keyword] | None = None,
        properties: Properties | None = None,
        logbook: Logbook | None = None,
        body: list[Element] | None = None,
        children: list[Heading] | None = None,
    ) -> None:
        self._filename = filename
        self._title = title
        self._author = author
        self._category = category
        self._description = description
        self._todo = todo
        self._keywords: dict[str, Keyword] = keywords if keywords is not None else {}
        self._properties = properties
        self._logbook = logbook
        self._body: list[Element] = body if body is not None else []
        self._children: list[Heading] = children if children is not None else []
        self._node: tree_sitter.Node | None = None
        self._source: bytes = b""
        self._dirty = False
        self._errors: list[ParseError] = []

        self._sync_keywords_with_dedicated()

        self._adopt_keyword(self._title)
        self._adopt_keyword(self._author)
        self._adopt_keyword(self._category)
        self._adopt_keyword(self._description)
        self._adopt_keyword(self._todo)
        self._adopt_keywords(self._keywords)
        self._adopt_properties(self._properties)
        self._adopt_logbook(self._logbook)
        self._adopt_body_elements(self._body)
        self._adopt_children(self._children)

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
        all_kw, properties, logbook, body = _parse_zeroth_section(root, parent=doc)
        doc._title = all_kw.get(_TITLE)
        doc._author = all_kw.get(_AUTHOR)
        doc._category = all_kw.get(_CATEGORY)
        doc._description = all_kw.get(_DESCRIPTION)
        doc._todo = all_kw.get(_TODO)
        doc._keywords = all_kw
        doc._properties = properties
        doc._logbook = logbook
        doc._body = body
        doc._adopt_keyword(doc._title)
        doc._adopt_keyword(doc._author)
        doc._adopt_keyword(doc._category)
        doc._adopt_keyword(doc._description)
        doc._adopt_keyword(doc._todo)
        doc._adopt_keywords(doc._keywords)
        doc._adopt_properties(doc._properties)
        doc._adopt_logbook(doc._logbook)
        doc._adopt_body_elements(doc._body)

        # --- build top-level headings ---------------------------------------
        for child in root.children:
            if child.type == _HEADING:
                heading = Heading.from_node(
                    child,
                    document=doc,
                    parent=doc,
                )
                doc._children.append(heading)

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
    def title(self) -> Keyword | None:
        """The ``#+TITLE:`` value, or *None*."""
        return self._title

    @title.setter
    def title(self, value: Keyword | None) -> None:
        """Set the ``#+TITLE:`` value and mark the document as dirty."""
        self._title = value
        if value is None:
            self._keywords.pop(_TITLE, None)
        else:
            self._keywords[_TITLE] = value
        self._adopt_keyword(self._title)
        self._mark_dirty()

    @property
    def author(self) -> Keyword | None:
        """The ``#+AUTHOR:`` value, or *None*."""
        return self._author

    @author.setter
    def author(self, value: Keyword | None) -> None:
        """Set the ``#+AUTHOR:`` value and mark the document as dirty."""
        self._author = value
        if value is None:
            self._keywords.pop(_AUTHOR, None)
        else:
            self._keywords[_AUTHOR] = value
        self._adopt_keyword(self._author)
        self._mark_dirty()

    @property
    def category(self) -> Keyword | None:
        """The ``#+CATEGORY:`` value, or *None*."""
        return self._category

    @category.setter
    def category(self, value: Keyword | None) -> None:
        """Set the ``#+CATEGORY:`` value and mark the document as dirty."""
        self._category = value
        if value is None:
            self._keywords.pop(_CATEGORY, None)
        else:
            self._keywords[_CATEGORY] = value
        self._adopt_keyword(self._category)
        self._mark_dirty()

    @property
    def description(self) -> Keyword | None:
        """The ``#+DESCRIPTION:`` value, or *None*."""
        return self._description

    @description.setter
    def description(self, value: Keyword | None) -> None:
        """Set the ``#+DESCRIPTION:`` value and mark the document as dirty."""
        self._description = value
        if value is None:
            self._keywords.pop(_DESCRIPTION, None)
        else:
            self._keywords[_DESCRIPTION] = value
        self._adopt_keyword(self._description)
        self._mark_dirty()

    @property
    def todo(self) -> Keyword | None:
        """The ``#+TODO:`` value, or *None*."""
        return self._todo

    @todo.setter
    def todo(self, value: Keyword | None) -> None:
        """Set the ``#+TODO:`` value and mark the document as dirty."""
        self._todo = value
        if value is None:
            self._keywords.pop(_TODO, None)
        else:
            self._keywords[_TODO] = value
        self._adopt_keyword(self._todo)
        self._mark_dirty()

    @property
    def keywords(self) -> dict[str, Keyword]:
        """Non-dedicated special keywords, keyed by upper-cased name."""
        return self._keywords

    @keywords.setter
    def keywords(self, value: dict[str, Keyword]) -> None:
        """Set non-dedicated keywords and mark the document as dirty."""
        self._keywords = value
        self._title = self._keywords.get(_TITLE)
        self._author = self._keywords.get(_AUTHOR)
        self._category = self._keywords.get(_CATEGORY)
        self._description = self._keywords.get(_DESCRIPTION)
        self._todo = self._keywords.get(_TODO)
        self._adopt_keyword(self._title)
        self._adopt_keyword(self._author)
        self._adopt_keyword(self._category)
        self._adopt_keyword(self._description)
        self._adopt_keyword(self._todo)
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
        self._adopt_properties(self._properties)
        self._mark_dirty()

    @property
    def logbook(self) -> Logbook | None:
        """Merged zeroth-section ``LOGBOOK`` drawer, or *None*."""
        return self._logbook

    @logbook.setter
    def logbook(self, value: Logbook | None) -> None:
        """Set merged ``LOGBOOK`` drawer and mark the document dirty."""
        self._logbook = value
        self._adopt_logbook(self._logbook)
        self._mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Zeroth-section body elements (excludes keywords and headings)."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set zeroth-section body elements and mark the document as dirty."""
        self._body = value
        self._adopt_body_elements(self._body)
        self._mark_dirty()

    @property
    def children(self) -> list[Heading]:
        """Top-level headings."""
        return self._children

    @children.setter
    def children(self, value: list[Heading]) -> None:
        """Set top-level headings and mark the document as dirty."""
        self._children = value
        self._adopt_children(self._children)
        self._mark_dirty()

    @property
    def source(self) -> bytes:
        """Original source bytes used to build this document."""
        return self._source

    @source.setter
    def source(self, value: bytes) -> None:
        """Set source bytes and mark the document as dirty."""
        self._source = value
        self._mark_dirty()

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
        """
        text = self._source[node.start_byte : node.end_byte].decode()
        self._errors.append(ParseError(node=node, text=text))

    def _mark_dirty(self) -> None:
        """Mark this document as dirty."""
        self._dirty = True

    def mark_dirty(self) -> None:
        """Mark this document as dirty.

        This public helper is intended for nested objects that need to bubble
        mutation state up to the owning document.
        """
        self._mark_dirty()

    def reformat(self) -> None:
        """Recursively mark document descendants dirty, then self dirty."""
        reformat_value(self._keywords)
        reformat_value(self._title)
        reformat_value(self._author)
        reformat_value(self._category)
        reformat_value(self._description)
        reformat_value(self._todo)
        reformat_value(self._properties)
        reformat_value(self._logbook)
        reformat_value(self._body)
        reformat_value(self._children)
        self.mark_dirty()

    def _adopt_keyword(self, value: Keyword | None) -> None:
        """Assign this document as parent for one keyword."""
        if value is None:
            return
        value.set_parent(self, mark_dirty=False)

    def _adopt_keywords(self, keywords: dict[str, Keyword]) -> None:
        """Assign this document as parent for all keyword entries."""
        for value in keywords.values():
            value.set_parent(self, mark_dirty=False)

    def _adopt_properties(self, value: Properties | None) -> None:
        """Assign this document as parent for merged properties drawer."""
        if value is None:
            return
        value.set_parent(self, mark_dirty=False)

    def _adopt_logbook(self, value: Logbook | None) -> None:
        """Assign this document as parent for merged logbook drawer."""
        if value is None:
            return
        value.set_parent(self, mark_dirty=False)

    def _sync_keywords_with_dedicated(self) -> None:
        """Ensure dedicated keyword properties and map stay aligned."""
        if self._title is None:
            self._title = self._keywords.get(_TITLE)
        else:
            self._keywords[_TITLE] = self._title

        if self._author is None:
            self._author = self._keywords.get(_AUTHOR)
        else:
            self._keywords[_AUTHOR] = self._author

        if self._category is None:
            self._category = self._keywords.get(_CATEGORY)
        else:
            self._keywords[_CATEGORY] = self._category

        if self._description is None:
            self._description = self._keywords.get(_DESCRIPTION)
        else:
            self._keywords[_DESCRIPTION] = self._description

        if self._todo is None:
            self._todo = self._keywords.get(_TODO)
        else:
            self._keywords[_TODO] = self._todo

    def _adopt_body_elements(self, body: list[Element]) -> None:
        """Assign this document as parent for all body elements."""
        for element in body:
            element.set_parent(self, mark_dirty=False)

    def _adopt_children(self, children: list[Heading]) -> None:
        """Assign this document as parent for all top-level headings."""
        for child in children:
            child.set_parent(self, mark_dirty=False)

    # -- dunder protocols ----------------------------------------------------

    def __str__(self) -> str:
        """Return a textual representation of the document zeroth section.

        When the document is clean and still backed by a parse tree, this
        returns the exact source slice for the zeroth section to preserve
        original whitespace and formatting. Once the document is dirty, this
        falls back to a reconstructed representation from semantic fields.
        """
        if not self._dirty and self._node is not None:
            zeroth = _find_first_child_by_type(self._node, _ZEROTH_SECTION)
            if zeroth is None:
                return ""
            return self._source[zeroth.start_byte : zeroth.end_byte].decode()

        return _render_document_dirty(self)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        parts = [f"filename={self._filename!r}"]
        if self._title is not None:
            parts.append(f"title={self._title!r}")
        if self._author is not None:
            parts.append(f"author={self._author!r}")
        if self._category is not None:
            parts.append(f"category={self._category!r}")
        if self._description is not None:
            parts.append(f"description={self._description!r}")
        if self._todo is not None:
            parts.append(f"todo={self._todo!r}")
        if self._keywords:
            parts.append(f"keywords={self._keywords!r}")
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
) -> tuple[dict[str, Keyword], Properties | None, Logbook | None, list[Element]]:
    """Extract all keywords and body elements from the zeroth section.

    Returns:
        A ``(keywords, properties, logbook, body)`` tuple. *keywords* maps
        upper-cased keyword names to :class:`Keyword` values. Dedicated
        drawer values are merged across repeated drawers. *body* contains
        non-keyword, non-dedicated-drawer elements.
    """
    from org_parser.document._body import (
        coalesce_list_items,
        extract_body_element,
        merge_logbook_drawers,
        merge_properties_drawers,
    )

    keywords: dict[str, Keyword] = {}
    property_drawers: list[Properties] = []
    logbook_drawers: list[Logbook] = []
    body: list[Element] = []

    for child in root.children:
        if child.type == _ZEROTH_SECTION:
            for sc in child.named_children:
                if sc.type == _SPECIAL_KEYWORD:
                    key, keyword = _extract_keyword(sc, parent=parent)
                    keywords[key] = keyword
                elif sc.type == _PROPERTY_DRAWER:
                    property_drawers.append(
                        Properties.from_node(sc, parent, parent=parent)
                    )
                elif sc.type == _LOGBOOK_DRAWER:
                    logbook_drawers.append(Logbook.from_node(sc, parent, parent=parent))
                elif sc.type == _DRAWER:
                    drawer = Drawer.from_node(sc, parent, parent=parent)
                    drawer_name = drawer.name.upper()
                    if drawer_name == "PROPERTIES":
                        property_drawers.append(Properties.from_drawer(drawer))
                    elif drawer_name == "LOGBOOK":
                        logbook_drawers.append(Logbook.from_drawer(drawer))
                    else:
                        body.append(drawer)
                else:
                    body.append(
                        extract_body_element(sc, parent=parent, document=parent)
                    )
            break  # only one zeroth section

    return (
        keywords,
        merge_properties_drawers(property_drawers, parent=parent),
        merge_logbook_drawers(logbook_drawers, parent=parent),
        coalesce_list_items(body, parent=parent),
    )


def _extract_keyword(
    kw_node: tree_sitter.Node,
    *,
    parent: Document,
) -> tuple[str, Keyword]:
    """Return ``(KEY, value)`` for a single ``special_keyword`` node.

    The key is upper-case normalised.
    """
    keyword = Keyword.from_node(kw_node, parent, parent=parent)
    return keyword.key, keyword


def _find_first_child_by_type(
    node: tree_sitter.Node,
    node_type: str,
) -> tree_sitter.Node | None:
    """Return the first direct child with the given type, if any."""
    for child in node.children:
        if child.type == node_type:
            return child
    return None


def _render_document_dirty(document: Document) -> str:
    """Render a dirty document from semantic fields only."""
    parts: list[str] = []

    dedicated_keywords = [
        document.title,
        document.author,
        document.category,
        document.description,
        document.todo,
    ]

    parts.extend(str(keyword) for keyword in dedicated_keywords if keyword is not None)
    parts.extend(
        str(keyword)
        for key, keyword in document.keywords.items()
        if key not in {_TITLE, _AUTHOR, _CATEGORY, _DESCRIPTION, _TODO}
    )

    if document.properties is not None:
        parts.append(str(document.properties))
    if document.logbook is not None:
        parts.append(str(document.logbook))

    parts.extend(str(element) for element in document.body)

    return "".join(parts)
