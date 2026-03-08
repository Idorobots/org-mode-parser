"""Implementation of :class:`Paragraph` for Org paragraph elements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._element import Element
from org_parser.text._rich_text import RichText

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["Paragraph"]


class Paragraph(Element):
    """Paragraph element that stores parsed rich-text body content.

    Args:
        body: Parsed paragraph body rich text.
        parent: Optional parent owner object.
        source_text: Optional verbatim source text.
    """

    def __init__(
        self,
        *,
        body: RichText,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(node_type="paragraph", source_text=source_text, parent=parent)
        self._body = body
        self._body.set_parent(self, mark_dirty=False)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        source: bytes,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Paragraph:
        """Create a :class:`Paragraph` from a tree-sitter ``paragraph`` node."""
        paragraph = cls(
            body=RichText.from_node(node, source),
            parent=parent,
            source_text=source[node.start_byte : node.end_byte].decode(),
        )
        paragraph._node = node
        return paragraph

    @property
    def body(self) -> RichText:
        """Mutable rich-text body of this paragraph."""
        return self._body

    @body.setter
    def body(self, value: RichText) -> None:
        """Set body rich text and mark this paragraph as dirty."""
        self._body = value
        self._body.set_parent(self, mark_dirty=False)
        self._mark_dirty()

    def __str__(self) -> str:
        """Render paragraph text.

        Clean parse-backed instances preserve their verbatim source text.
        Dirty instances are rendered from semantic body text.
        """
        if not self.dirty and self._node is not None:
            return self.source_text
        return str(self._body)

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"Paragraph(body={str(self._body)!r})"
