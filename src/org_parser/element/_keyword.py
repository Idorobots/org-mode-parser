"""Implementation of :class:`Keyword` for Org special keyword lines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._element import Element, node_source
from org_parser.text._rich_text import RichText

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["Keyword"]


class Keyword(Element):
    """Special keyword element, e.g. ``#+TITLE: Value``.

    Args:
        key: Upper-cased keyword key.
        value: Keyword value rich text.
        parent: Optional parent owner object.
    """

    def __init__(
        self,
        *,
        key: str,
        value: RichText,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._key = key.upper()
        self._value = value
        self._value.parent = self

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document | None = None,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Keyword:
        """Create a :class:`Keyword` from a tree-sitter ``special_keyword`` node.

        Args:
            node: The ``special_keyword`` tree-sitter node.
            document: The owning :class:`Document`, or *None* for programmatic
                construction (source defaults to ``b""``).
            parent: Optional parent owner object.
        """
        source = document.source if document is not None else b""
        key_node = node.child_by_field_name("key")
        key = (
            key_node.text.decode().upper()
            if key_node is not None and key_node.text is not None
            else ""
        )

        value_node = node.child_by_field_name("value")
        value = (
            RichText.from_node(value_node, source, document=document)
            if value_node is not None
            else RichText("")
        )

        kw = cls(key=key, value=value, parent=parent)
        kw._node = node
        kw._document = document
        return kw

    @property
    def key(self) -> str:
        """The upper-cased keyword key."""
        return self._key

    @key.setter
    def key(self, value: str) -> None:
        """Set keyword key and mark as dirty."""
        self._key = value.upper()
        self._mark_dirty()

    @property
    def value(self) -> RichText:
        """The mutable keyword value rich text."""
        return self._value

    @value.setter
    def value(self, value: RichText) -> None:
        """Set keyword value and mark as dirty."""
        self._value = value
        self._value.parent = self
        self._mark_dirty()

    def reformat(self) -> None:
        """Mark value and this keyword dirty for scratch-built rendering."""
        self._value.reformat()
        self.mark_dirty()

    def __str__(self) -> str:
        """Render keyword line.

        Clean parse-backed instances preserve their verbatim source text.
        Dirty instances are rendered from semantic fields.
        """
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        rendered_value = str(self._value)
        if rendered_value == "":
            return f"#+{self._key}:\n"
        return f"#+{self._key}: {rendered_value}\n"

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"Keyword(key={self._key!r}, value={self._value!r})"
