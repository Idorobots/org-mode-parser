"""Stub implementation of :class:`Element` — a structural building block.

An :class:`Element` wraps a tree-sitter node that represents an Org Mode
*greater element* or *lesser element* (paragraph, plain list, source block,
drawer, etc.).  This stub captures only the node type and verbatim source
text; richer per-element semantics will be added in later iterations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

__all__ = ["Element"]


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
    ) -> None:
        self._node_type = node_type
        self._source_text = source_text
        self._node: tree_sitter.Node | None = None
        self._dirty = False

    # -- factory method ------------------------------------------------------

    @classmethod
    def from_node(cls, node: tree_sitter.Node, source: bytes) -> Element:
        """Create an :class:`Element` from a tree-sitter node.

        Args:
            node: The tree-sitter node to wrap.
            source: The full source bytes of the document.

        Returns:
            A new :class:`Element` preserving the node type and verbatim
            source text.
        """
        elem = cls(
            node_type=node.type,
            source_text=source[node.start_byte : node.end_byte].decode(),
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
    def dirty(self) -> bool:
        """Whether this element has been mutated after creation."""
        return self._dirty

    def _mark_dirty(self) -> None:
        """Mark this element as dirty."""
        self._dirty = True

    def mark_dirty(self) -> None:
        """Mark this element as dirty."""
        self._mark_dirty()

    # -- dunder protocols ----------------------------------------------------

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        text_preview = self._source_text[:40]
        if len(self._source_text) > 40:
            text_preview += "…"
        return f"Element(node_type={self._node_type!r}, text={text_preview!r})"
