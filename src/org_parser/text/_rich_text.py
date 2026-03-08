"""Stub implementation of :class:`RichText` — verbatim rich-text content.

A :class:`RichText` instance holds the raw source text extracted from one or
more tree-sitter nodes.  Future iterations will expose the individual inline
objects (bold, italic, links, …) that compose the text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    import tree_sitter

__all__ = ["RichText"]


class RichText:
    """Verbatim rich-text content from an Org Mode document.

    This is currently a thin wrapper around a plain string.  The raw source
    representation is preserved exactly as it appears in the parse tree so
    that future mutations can reconstruct an accurate textual form.

    Args:
        text: The raw source text.
    """

    def __init__(self, text: str) -> None:
        self._text = text
        self._node: tree_sitter.Node | None = None
        self._dirty = False

    @property
    def text(self) -> str:
        """Raw text content."""
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        """Set raw text content and mark rich text as dirty."""
        self._text = value
        self._mark_dirty()

    @property
    def dirty(self) -> bool:
        """Whether this rich text has been mutated after creation."""
        return self._dirty

    def _mark_dirty(self) -> None:
        """Mark this rich text as dirty."""
        self._dirty = True

    def mark_dirty(self) -> None:
        """Mark this rich text as dirty."""
        self._mark_dirty()

    # -- factory methods -----------------------------------------------------

    @classmethod
    def from_node(cls, node: tree_sitter.Node, source: bytes) -> RichText:
        """Create a :class:`RichText` from a single tree-sitter node.

        Args:
            node: The tree-sitter node whose byte range supplies the text.
            source: The full source bytes of the document.

        Returns:
            A new :class:`RichText` with verbatim text extracted from
            *source*.
        """
        rt = cls(source[node.start_byte : node.end_byte].decode())
        rt._node = node
        return rt

    @classmethod
    def from_nodes(
        cls,
        nodes: Sequence[tree_sitter.Node],
        source: bytes,
    ) -> RichText | None:
        """Create a :class:`RichText` spanning multiple contiguous nodes.

        The text is taken as the verbatim byte range from the start of the
        first node to the end of the last node.

        Args:
            nodes: An ordered, non-overlapping sequence of tree-sitter nodes.
                If the sequence is empty, *None* is returned.
            source: The full source bytes of the document.

        Returns:
            A new :class:`RichText`, or *None* when *nodes* is empty.
        """
        if not nodes:
            return None
        first = nodes[0]
        last = nodes[-1]
        rt = cls(source[first.start_byte : last.end_byte].decode())
        # Store the first node as a representative for later tree access.
        rt._node = first
        return rt

    # -- dunder protocols ----------------------------------------------------

    def __str__(self) -> str:
        """Return the raw text content."""
        return self._text

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"RichText({self._text!r})"

    def __eq__(self, other: object) -> bool:
        """Compare by text content."""
        if isinstance(other, RichText):
            return self._text == other._text
        if isinstance(other, str):
            return self._text == other
        return NotImplemented

    def __hash__(self) -> int:
        """Hash by text content."""
        return hash(self._text)
