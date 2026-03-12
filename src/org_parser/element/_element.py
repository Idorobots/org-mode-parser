"""Stub implementation of :class:`Element` — a structural building block.

An :class:`Element` wraps a tree-sitter node that represents an Org Mode
*greater element* or *lesser element* (paragraph, plain list, source block,
drawer, etc.).  This stub captures only the node type and verbatim source
text; richer per-element semantics will be added in later iterations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["Element", "reformat_value"]

_ERROR_NODE_TYPE = "ERROR"


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


def reformat_value(value: object) -> None:
    """Recursively mark semantic nodes dirty for scratch-built rendering."""
    if value is None:
        return

    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        for nested in mapping.values():
            reformat_value(nested)
        return

    if isinstance(value, list | tuple | set):
        sequence = cast(list[object] | tuple[object, ...] | set[object], value)
        for nested in sequence:
            reformat_value(nested)
        return

    reformat = getattr(value, "reformat", None)
    if callable(reformat):
        reformat()
        return

    mark_dirty = getattr(value, "mark_dirty", None)
    if callable(mark_dirty):
        mark_dirty()


class Element:
    """Stub for an Org Mode element node.

    Args:
        node_type: The tree-sitter node type name (e.g. ``"paragraph"``).
        source_text: The verbatim source text of the element.
    """

    def __init__(
        self,
        *,
        node_type: str = "",
        source_text: str = "",
        parent: Document | Heading | Element | None = None,
    ) -> None:
        self._node_type = node_type
        self._source_text = source_text
        self._parent = parent
        self._node: tree_sitter.Node | None = None
        self._dirty = False

    # -- factory method ------------------------------------------------------

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document | None = None,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Element:
        """Create an :class:`Element` from a tree-sitter node.

        Args:
            node: The tree-sitter node to wrap.
            document: The owning :class:`Document`, or *None* for programmatic
                construction (source defaults to ``b""``).
            parent: Optional parent object that owns this element.

        Returns:
            A new :class:`Element` preserving the node type and verbatim
            source text.
        """
        source = document.source if document is not None else b""
        elem = cls(
            node_type=node.type,
            source_text=source[node.start_byte : node.end_byte].decode(),
            parent=parent,
        )
        elem._node = node
        return elem

    # -- public read-only properties -----------------------------------------

    @property
    def node_type(self) -> str:
        """The tree-sitter node type name."""
        return self._node_type

    @node_type.setter
    def node_type(self, value: str) -> None:
        """Set the node type and mark the element as dirty."""
        self._node_type = value
        self._mark_dirty()

    @property
    def source_text(self) -> str:
        """The verbatim source text of the element."""
        return self._source_text

    @source_text.setter
    def source_text(self, value: str) -> None:
        """Set source text and mark the element as dirty."""
        self._source_text = value
        self._mark_dirty()

    @property
    def parent(self) -> Document | Heading | Element | None:
        """Parent object that contains this element, if any."""
        return self._parent

    @parent.setter
    def parent(self, value: Document | Heading | Element | None) -> None:
        """Set the parent object and mark this element as dirty."""
        self.set_parent(value)

    def set_parent(
        self,
        value: Document | Heading | Element | None,
        *,
        mark_dirty: bool = True,
    ) -> None:
        """Set parent object with optional dirty propagation."""
        self._parent = value
        if mark_dirty:
            self._mark_dirty()

    @property
    def dirty(self) -> bool:
        """Whether this element has been mutated after creation."""
        return self._dirty

    def _mark_dirty(self) -> None:
        """Mark this element dirty and bubble to parent objects."""
        if self._dirty:
            return
        self._dirty = True
        parent = self._parent
        if parent is None:
            return
        dirty_parent = parent
        if not dirty_parent.dirty:
            dirty_parent.mark_dirty()

    def mark_dirty(self) -> None:
        """Mark this element as dirty."""
        self._mark_dirty()

    def reformat(self) -> None:
        """Recursively mark descendants dirty, then mark this element dirty."""
        for key, value in vars(self).items():
            if key in {
                "_parent",
                "_node",
                "_dirty",
                "_source_text",
                "_node_type",
            }:
                continue
            reformat_value(value)
        self.mark_dirty()

    # -- dunder protocols ----------------------------------------------------

    def __str__(self) -> str:
        """Return the element text representation.

        This is currently a simple passthrough of the stored source text while
        element-specific reconstruction is still a stub.
        """
        return self._source_text

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"Element(node_type={self._node_type!r})"


# ---------------------------------------------------------------------------
# Shared node utilities
# ---------------------------------------------------------------------------


def _is_error_node(node: tree_sitter.Node) -> bool:
    """Return *True* if *node* is a parse-error or missing token.

    Args:
        node: Any tree-sitter node to inspect.

    Returns:
        ``True`` for ``ERROR``-typed nodes and for nodes where
        ``node.is_missing`` is set by the parser's error-recovery.
    """
    return node.type == _ERROR_NODE_TYPE or node.is_missing


def element_from_error_or_unknown(
    node: tree_sitter.Node,
    document: Document | None = None,
    *,
    parent: Document | Heading | Element | None = None,
) -> Element:
    """Return a semantic element for an unrecognised or error parse node.

    Error and missing nodes are recovered as a
    :class:`~org_parser.element._paragraph.Paragraph` whose ``body`` is a
    :class:`~org_parser.text._rich_text.RichText` of the verbatim source
    text.  The owning :class:`~org_parser.document._document.Document`'s
    :meth:`~org_parser.document._document.Document.report_error` method is
    invoked so the document can record the error.

    Unknown but syntactically valid nodes fall back to the generic
    :class:`Element` stub (preserving the existing behaviour).

    Args:
        node: The unrecognised tree-sitter node.
        document: The owning :class:`Document`, or *None* for programmatic
            construction (source defaults to ``b""``).
        parent: Optional owner object.

    Returns:
        A :class:`~org_parser.element._paragraph.Paragraph` for error nodes,
        or a plain :class:`Element` for unknown valid nodes.
    """
    if _is_error_node(node):
        if document is not None:
            document.report_error(node)
        # Lazy imports avoid the circular dependency
        # (_paragraph imports Element; _rich_text imports time/).
        from org_parser.element._paragraph import Paragraph
        from org_parser.text._rich_text import RichText

        source = document.source if document is not None else b""
        text = source[node.start_byte : node.end_byte].decode()
        return Paragraph(body=RichText(text), source_text=text, parent=parent)
    return Element.from_node(node, document, parent=parent)


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
