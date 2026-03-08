"""Implementation of :class:`Document` — a full Org Mode document."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._element import Element
from org_parser.text._rich_text import RichText

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._heading import Heading

__all__ = ["Document"]

# Node type names produced by the tree-sitter grammar.
_ZEROTH_SECTION = "zeroth_section"
_HEADING = "heading"
_SPECIAL_KEYWORD = "special_keyword"


class Document:
    """Representation of a full Org Mode document.

    A :class:`Document` exposes the zeroth-section body elements, top-level
    headings, and well-known keyword properties (``TITLE``, ``AUTHOR``, etc.)
    parsed from the file.

    Args:
        filename: The filename of the document.
        title: The ``#+TITLE:`` value, or *None*.
        author: The ``#+AUTHOR:`` value, or *None*.
        category: The ``#+CATEGORY:`` value, or *None*.
        description: The ``#+DESCRIPTION:`` value, or *None*.
        todo: The ``#+TODO:`` value, or *None*.
        keywords: Remaining special keywords not covered by the dedicated
            properties, keyed by upper-cased keyword name.
        body: Zeroth-section elements (excluding headings and special
            keywords).
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
        keywords: dict[str, RichText] | None = None,
        body: list[Element] | None = None,
        children: list[Heading] | None = None,
    ) -> None:
        self._filename = filename
        self._title = title
        self._author = author
        self._category = category
        self._description = description
        self._todo = todo
        self._keywords: dict[str, RichText] = keywords if keywords is not None else {}
        self._body: list[Element] = body if body is not None else []
        self._children: list[Heading] = children if children is not None else []
        self._node: tree_sitter.Node | None = None
        self._source: bytes = b""
        self._dirty = False

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

        # --- extract zeroth-section data ------------------------------------
        all_kw, body = _parse_zeroth_section(root, source)

        # Pop dedicated keywords; everything left stays in the generic dict.
        doc = cls(
            filename=filename,
            title=all_kw.pop("TITLE", None),
            author=all_kw.pop("AUTHOR", None),
            category=all_kw.pop("CATEGORY", None),
            description=all_kw.pop("DESCRIPTION", None),
            todo=all_kw.pop("TODO", None),
            keywords=all_kw,
            body=body,
        )
        doc._node = root
        doc._source = source

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
    def title(self) -> RichText | None:
        """The ``#+TITLE:`` value, or *None*."""
        return self._title

    @title.setter
    def title(self, value: RichText | None) -> None:
        """Set the ``#+TITLE:`` value and mark the document as dirty."""
        self._title = value
        self._mark_dirty()

    @property
    def author(self) -> RichText | None:
        """The ``#+AUTHOR:`` value, or *None*."""
        return self._author

    @author.setter
    def author(self, value: RichText | None) -> None:
        """Set the ``#+AUTHOR:`` value and mark the document as dirty."""
        self._author = value
        self._mark_dirty()

    @property
    def category(self) -> RichText | None:
        """The ``#+CATEGORY:`` value, or *None*."""
        return self._category

    @category.setter
    def category(self, value: RichText | None) -> None:
        """Set the ``#+CATEGORY:`` value and mark the document as dirty."""
        self._category = value
        self._mark_dirty()

    @property
    def description(self) -> RichText | None:
        """The ``#+DESCRIPTION:`` value, or *None*."""
        return self._description

    @description.setter
    def description(self, value: RichText | None) -> None:
        """Set the ``#+DESCRIPTION:`` value and mark the document as dirty."""
        self._description = value
        self._mark_dirty()

    @property
    def todo(self) -> RichText | None:
        """The ``#+TODO:`` value, or *None*."""
        return self._todo

    @todo.setter
    def todo(self, value: RichText | None) -> None:
        """Set the ``#+TODO:`` value and mark the document as dirty."""
        self._todo = value
        self._mark_dirty()

    @property
    def keywords(self) -> dict[str, RichText]:
        """Non-dedicated special keywords, keyed by upper-cased name."""
        return self._keywords

    @keywords.setter
    def keywords(self, value: dict[str, RichText]) -> None:
        """Set non-dedicated keywords and mark the document as dirty."""
        self._keywords = value
        self._mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Zeroth-section body elements (excludes keywords and headings)."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set zeroth-section body elements and mark the document as dirty."""
        self._body = value
        self._mark_dirty()

    @property
    def children(self) -> list[Heading]:
        """Top-level headings."""
        return self._children

    @children.setter
    def children(self, value: list[Heading]) -> None:
        """Set top-level headings and mark the document as dirty."""
        self._children = value
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

    # -- dunder protocols ----------------------------------------------------

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
) -> tuple[dict[str, RichText], list[Element]]:
    """Extract all keywords and body elements from the zeroth section.

    Returns:
        A ``(keywords, body)`` pair.  *keywords* maps upper-cased keyword
        names to their :class:`RichText` values (last-one-wins for
        duplicates).  *body* contains non-keyword elements.
    """
    keywords: dict[str, RichText] = {}
    body: list[Element] = []

    for child in root.children:
        if child.type == _ZEROTH_SECTION:
            for sc in child.named_children:
                if sc.type == _SPECIAL_KEYWORD:
                    key, value = _extract_keyword(sc, source)
                    keywords[key] = value
                else:
                    body.append(Element.from_node(sc, source))
            break  # only one zeroth section

    return keywords, body


def _extract_keyword(
    kw_node: tree_sitter.Node,
    source: bytes,
) -> tuple[str, RichText]:
    """Return ``(KEY, value)`` for a single ``special_keyword`` node.

    The key is upper-case normalised.  If the keyword has no value part an
    empty :class:`RichText` is returned.
    """
    key_node = kw_node.child_by_field_name("key")
    key = (
        key_node.text.decode().upper()
        if key_node is not None and key_node.text is not None
        else ""
    )

    value_node = kw_node.child_by_field_name("value")
    value = (
        RichText.from_node(value_node, source)
        if value_node is not None
        else RichText("")
    )

    return key, value
