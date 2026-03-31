"""Implementation of [org_parser.element.Paragraph][] for Org paragraph elements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._element import Element, build_semantic_repr, node_source
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

    Example:
    ```python
    >>> from org_parser.element import Paragraph
    >>> paragraph = Paragraph.from_source("Paragraph text")
    >>> paragraph.body_text
    'Paragraph text'
    ```
    """

    def __init__(
        self,
        *,
        body: RichText,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._body = body
        self._body.parent = self

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Paragraph:
        """Create a [org_parser.element.Paragraph][] from a tree-sitter ``paragraph`` node.

        Args:
            node: The ``paragraph`` tree-sitter node.
            document: The owning [org_parser.document.Document][], or *None* for programmatic
                construction (source defaults to ``b""``).
            parent: Optional parent owner object.
        """
        paragraph = cls(
            body=RichText.from_node(node, document=document),
            parent=parent,
        )
        paragraph._node = node
        paragraph._document = document
        return paragraph

    @property
    def body(self) -> RichText:
        """Mutable rich-text body of this paragraph."""
        return self._body

    @body.setter
    def body(self, value: RichText) -> None:
        """Set body rich text."""
        self._body = value
        self._body.parent = self
        self.mark_dirty()

    @property
    def body_text(self) -> str:
        """Stringified text of the paragraph body."""
        return str(self._body)

    def reformat(self) -> None:
        """Mark body and this paragraph dirty for scratch-built rendering."""
        self._body.reformat()
        self.mark_dirty()

    def __str__(self) -> str:
        """Render paragraph text.

        Clean parse-backed instances preserve their verbatim source text.
        Dirty instances are rendered from semantic body text.
        """
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        return str(self._body)

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return build_semantic_repr("Paragraph", body=self._body)
