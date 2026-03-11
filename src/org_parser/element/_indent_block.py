"""Semantic wrapper for grammar ``block`` indentation nodes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._element import Element, build_semantic_repr

if TYPE_CHECKING:
    from collections.abc import Sequence

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["IndentBlock"]


class IndentBlock(Element):
    """Indentation wrapper node with nested body elements.

    Grammar ``block`` nodes represent one contiguous indented chunk.
    """

    def __init__(
        self,
        *,
        body: list[Element] | None = None,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(node_type="block", source_text=source_text, parent=parent)
        self._body = body if body is not None else []
        self._adopt_body(self._body)

    @property
    def body(self) -> list[Element]:
        """Nested elements contained by this indentation block."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set nested elements and mark this block dirty."""
        self._body = value
        self._adopt_body(self._body)
        self._mark_dirty()

    def _adopt_body(self, body: Sequence[Element]) -> None:
        """Assign this block as parent for all nested elements."""
        for element in body:
            element.set_parent(self, mark_dirty=False)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("IndentBlock", body=self._body)
