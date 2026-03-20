"""Implementation of :class:`Paragraph` for Org paragraph elements."""

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
        indent: Leading indentation of the first paragraph line, if present.
        parent: Optional parent owner object.
    """

    def __init__(
        self,
        *,
        body: RichText,
        indent: str | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._body = body
        self._indent = indent
        self._body.parent = self

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Paragraph:
        """Create a :class:`Paragraph` from a tree-sitter ``paragraph`` node.

        Args:
            node: The ``paragraph`` tree-sitter node.
            document: The owning :class:`Document`, or *None* for programmatic
                construction (source defaults to ``b""``).
            parent: Optional parent owner object.
        """
        paragraph = cls(
            body=RichText.from_node(node, document=document),
            indent=_extract_indent(node, document),
            parent=parent,
        )
        paragraph._node = node
        paragraph._document = document
        return paragraph

    @property
    def indent(self) -> str | None:
        """Leading indentation of the first paragraph line, if present."""
        return self._indent

    @indent.setter
    def indent(self, value: str | None) -> None:
        """Set paragraph indentation and mark the paragraph as dirty."""
        self._indent = value
        self._mark_dirty()

    @property
    def body(self) -> RichText:
        """Mutable rich-text body of this paragraph."""
        return self._body

    @body.setter
    def body(self, value: RichText) -> None:
        """Set body rich text and mark this paragraph as dirty."""
        self._body = value
        self._body.parent = self
        self._mark_dirty()

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
        return build_semantic_repr("Paragraph", body=self._body, indent=self._indent)


def _extract_indent(node: tree_sitter.Node, document: Document) -> str | None:
    """Return paragraph first-line indentation from parse field, if present."""
    field_node = node.child_by_field_name("indent")
    if field_node is None:
        return None
    value = document.source_for(field_node).decode()
    return value if value != "" else None
