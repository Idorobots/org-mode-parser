"""Base class for Org Mode structural element nodes.

An :class:`Element` wraps a tree-sitter node that represents an Org Mode
*greater element* or *lesser element* (paragraph, plain list, source block,
drawer, etc.).  Concrete subclasses add per-element semantic fields;
:class:`Element` itself should not be instantiated directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from org_parser._node import node_source

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading
    from org_parser.element._keyword import AffiliatedKeyword

__all__ = ["Element", "node_source"]

_ElementT = TypeVar("_ElementT", bound="Element")


def build_semantic_repr(class_name: str, /, **fields: object) -> str:
    """Build a compact repr omitting ``None`` and empty-list fields."""
    parts = [
        f"{name}={value!r}"
        for name, value in fields.items()
        if value is not None and not (isinstance(value, list) and not value)
    ]
    if not parts:
        return f"{class_name}()"
    return f"{class_name}({', '.join(parts)})"


class Element:
    """Base class for an Org Mode element node.

    Concrete subclasses represent specific element types (paragraph, list,
    drawer, block, etc.).  This class should not be instantiated directly.

    Args:
        parent: Optional parent object that owns this element.
    """

    def __init__(
        self,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        self._parent = parent
        self._node: tree_sitter.Node | None = None
        self._document: Document | None = None
        self._dirty = False
        self._keywords: list[AffiliatedKeyword] | None = None

    @classmethod
    def from_source(cls: type[_ElementT], source: str) -> _ElementT:
        """Parse *source* and return one strict semantic element.

        The source must parse to exactly one non-heading semantic element.

        Args:
            source: Org source text containing exactly one element.

        Returns:
            The parsed semantic element instance.

        Raises:
            ValueError: If parsing fails, structure is not exactly one element,
                or the parsed element does not match *cls*.
        """
        from org_parser._from_source import parse_document_from_source

        document = parse_document_from_source(source)
        if document.children:
            raise ValueError("Unexpected parse tree structure")

        semantic_nodes: list[Element] = []
        semantic_nodes.extend(document.keywords)
        if document.properties is not None:
            semantic_nodes.append(document.properties)
        if document.logbook is not None:
            semantic_nodes.append(document.logbook)
        semantic_nodes.extend(document.body)

        if len(semantic_nodes) != 1:
            raise ValueError("Unexpected parse tree structure")

        semantic_node: Element = semantic_nodes[0]
        if not isinstance(semantic_node, cls):
            raise ValueError(
                f"Parsed element is {semantic_node.__class__.__name__}, "
                f"expected {cls.__name__}"
            )
        return semantic_node

    # -- public read-only properties -----------------------------------------

    @property
    def parent(self) -> Document | Heading | Element | None:
        """Parent object that contains this element, if any."""
        return self._parent

    @parent.setter
    def parent(self, value: Document | Heading | Element | None) -> None:
        """Set the parent object without changing dirty state."""
        self._parent = value

    @property
    def dirty(self) -> bool:
        """Whether this element has been mutated after creation."""
        return self._dirty

    @property
    def text(self) -> str:
        """Stringified text representation of this element."""
        return str(self)

    @property
    def body_text(self) -> str:
        """Stringified body text for elements that implement body content."""
        return ""

    @property
    def keywords(self) -> list[AffiliatedKeyword]:
        """Affiliated keywords attached to this element, in document order.

        Affiliated keywords (``#+CAPTION:``, ``#+TBLNAME:``, ``#+PLOT:``,
        ``#+RESULTS:``) that immediately precede this element in the document
        body are linked here during parsing.  The list is empty when no
        affiliated keywords precede this element.

        The keywords remain as independent elements in the containing body
        list and are not duplicated in the serialised output of this element.
        """
        return self._keywords if self._keywords is not None else []

    def attach_keyword(self, keyword: AffiliatedKeyword) -> None:
        """Attach an affiliated keyword to this element without marking it dirty.

        This method is called during body post-processing to link affiliated
        keywords (``#+CAPTION:``, ``#+TBLNAME:``, ``#+PLOT:``,
        ``#+RESULTS:``) to the element that immediately follows them.  The
        keyword is appended to :attr:`keywords` in document order.

        Args:
            keyword: The affiliated keyword to attach.
        """
        if self._keywords is None:
            self._keywords = []
        self._keywords.append(keyword)

    def mark_dirty(self) -> None:
        """Mark this element as dirty."""
        if self._dirty:
            return
        self._dirty = True
        parent = self._parent
        if parent is None:
            return
        parent.mark_dirty()

    def attach_source(
        self,
        node: tree_sitter.Node,
        document: Document | None,
    ) -> None:
        """Attach parse-tree source backing to this element.

        This method is for internal factory use — call it immediately after
        construction to wire up the parse-tree node and owning document.

        Args:
            node: The tree-sitter node this element was built from.
            document: The owning :class:`Document`, or *None*.
        """
        self._node = node
        self._document = document

    def reformat(self) -> None:
        """Mark this element dirty for scratch-built rendering."""
        self.mark_dirty()

    # -- dunder protocols ----------------------------------------------------

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return "Element()"


# ---------------------------------------------------------------------------
# Shared node utilities
# ---------------------------------------------------------------------------


def element_from_error_or_unknown(
    node: tree_sitter.Node,
    document: Document | None = None,
    *,
    parent: Document | Heading | Element | None = None,
) -> Element:
    """Return a semantic element for an unrecognised or error parse node.

    All unrecognised nodes — whether a parser ``ERROR``, a missing token, or
    an unknown but syntactically valid node type — are recovered as a
    :class:`~org_parser.element._paragraph.Paragraph` whose ``body`` is a
    :class:`~org_parser.text._rich_text.RichText` of the verbatim source
    text.  The owning :class:`~org_parser.document._document.Document`'s
    :meth:`~org_parser.document._document.Document.report_error` method is
    invoked so the document can record the error.

    Args:
        node: The unrecognised tree-sitter node.
        document: The owning :class:`Document`, or *None* for programmatic
            construction (source defaults to ``b""``).
        parent: Optional owner object.

    Returns:
        A :class:`~org_parser.element._paragraph.Paragraph` wrapping the
        verbatim source text of *node*.
    """
    if document is not None:
        document.report_error(node)
    # Lazy imports avoid the circular dependency
    # (_paragraph imports Element; _rich_text imports time/).
    from org_parser.element._paragraph import Paragraph
    from org_parser.text._rich_text import RichText

    text = node_source(node, document)
    paragraph = Paragraph(body=RichText(text), parent=parent)
    paragraph.attach_source(node, document)
    return paragraph


def ensure_trailing_newline(value: str) -> str:
    r"""Return *value* with exactly one trailing newline when non-empty.

    Args:
        value: Any string, possibly without a trailing newline.

    Returns:
        The original string unchanged if empty or already newline-terminated;
        otherwise the string with one ``\n`` appended.
    """
    if value == "" or value.endswith("\n"):
        return value
    return f"{value}\n"
