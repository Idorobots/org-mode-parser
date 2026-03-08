"""Implementation of :class:`Document` — a full Org Mode document."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._element import Element
from org_parser.element._keyword import Keyword
from org_parser.element._paragraph import Paragraph

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._heading import Heading

__all__ = ["Document"]

# Node type names produced by the tree-sitter grammar.
_ZEROTH_SECTION = "zeroth_section"
_HEADING = "heading"
_SPECIAL_KEYWORD = "special_keyword"
_PARAGRAPH = "paragraph"
_TITLE = "TITLE"
_AUTHOR = "AUTHOR"
_CATEGORY = "CATEGORY"
_DESCRIPTION = "DESCRIPTION"
_TODO = "TODO"


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
        body: Zeroth-section elements (excluding headings and special
            keywords).
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
        self._body: list[Element] = body if body is not None else []
        self._children: list[Heading] = children if children is not None else []
        self._node: tree_sitter.Node | None = None
        self._source: bytes = b""
        self._dirty = False

        self._sync_keywords_with_dedicated()

        self._adopt_keyword(self._title)
        self._adopt_keyword(self._author)
        self._adopt_keyword(self._category)
        self._adopt_keyword(self._description)
        self._adopt_keyword(self._todo)
        self._adopt_keywords(self._keywords)
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
        all_kw, body = _parse_zeroth_section(root, source, parent=doc)
        doc._title = all_kw.get(_TITLE)
        doc._author = all_kw.get(_AUTHOR)
        doc._category = all_kw.get(_CATEGORY)
        doc._description = all_kw.get(_DESCRIPTION)
        doc._todo = all_kw.get(_TODO)
        doc._keywords = all_kw
        doc._body = body
        doc._adopt_keyword(doc._title)
        doc._adopt_keyword(doc._author)
        doc._adopt_keyword(doc._category)
        doc._adopt_keyword(doc._description)
        doc._adopt_keyword(doc._todo)
        doc._adopt_keywords(doc._keywords)
        doc._adopt_body_elements(doc._body)

        # --- build top-level headings ---------------------------------------
        for child in root.children:
            if child.type == _HEADING:
                heading = Heading.from_node(
                    child,
                    document=doc,
                    parent=doc,
                    source=source,
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

    def _mark_dirty(self) -> None:
        """Mark this document as dirty."""
        self._dirty = True

    def mark_dirty(self) -> None:
        """Mark this document as dirty.

        This public helper is intended for nested objects that need to bubble
        mutation state up to the owning document.
        """
        self._mark_dirty()

    def _adopt_keyword(self, value: Keyword | None) -> None:
        """Assign this document as parent for one keyword."""
        if value is None:
            return
        value.set_parent(self, mark_dirty=False)

    def _adopt_keywords(self, keywords: dict[str, Keyword]) -> None:
        """Assign this document as parent for all keyword entries."""
        for value in keywords.values():
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
        """Return a developer-friendly representation."""
        return (
            f"Document(filename={self._filename!r}, " f"headings={len(self._children)})"
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_zeroth_section(
    root: tree_sitter.Node,
    source: bytes,
    *,
    parent: Document,
) -> tuple[dict[str, Keyword], list[Element]]:
    """Extract all keywords and body elements from the zeroth section.

    Returns:
        A ``(keywords, body)`` pair.  *keywords* maps upper-cased keyword
        names to their :class:`Keyword` values (last-one-wins for
        duplicates).  *body* contains non-keyword elements.
    """
    keywords: dict[str, Keyword] = {}
    body: list[Element] = []

    for child in root.children:
        if child.type == _ZEROTH_SECTION:
            for sc in child.named_children:
                if sc.type == _SPECIAL_KEYWORD:
                    key, keyword = _extract_keyword(sc, source, parent=parent)
                    keywords[key] = keyword
                else:
                    body.append(_extract_body_element(sc, source, parent=parent))
            break  # only one zeroth section

    return keywords, body


def _extract_keyword(
    kw_node: tree_sitter.Node,
    source: bytes,
    *,
    parent: Document,
) -> tuple[str, Keyword]:
    """Return ``(KEY, value)`` for a single ``special_keyword`` node.

    The key is upper-case normalised.
    """
    keyword = Keyword.from_node(kw_node, source, parent=parent)
    return keyword.key, keyword


def _extract_body_element(
    node: tree_sitter.Node,
    source: bytes,
    *,
    parent: Document,
) -> Element:
    """Build one body element instance from a tree-sitter node."""
    if node.type == _PARAGRAPH:
        return Paragraph.from_node(node, source, parent=parent)
    return Element.from_node(node, source, parent=parent)


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

    parts.extend(str(element) for element in document.body)

    return "".join(parts)
