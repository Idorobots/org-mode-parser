"""Implementation of :class:`Keyword` for Org special keyword lines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._element import Element
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
        source_text: Optional verbatim source text.
    """

    def __init__(
        self,
        *,
        key: str,
        value: RichText,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(
            node_type="special_keyword",
            source_text=source_text,
            parent=parent,
        )
        self._key = key.upper()
        self._value = value
        self._value.set_parent(self, mark_dirty=False)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        source: bytes,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Keyword:
        """Create a :class:`Keyword` from a tree-sitter ``special_keyword`` node."""
        key_node = node.child_by_field_name("key")
        key = (
            key_node.text.decode().upper()
            if key_node is not None and key_node.text is not None
            else ""
        )

        value_node = node.child_by_field_name("value")
        value = (
            RichText.from_node(value_node, source)
            if value_node is not None
            else RichText("")
        )

        kw = cls(
            key=key,
            value=value,
            parent=parent,
            source_text=source[node.start_byte : node.end_byte].decode(),
        )
        kw._node = node
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
        self._value.set_parent(self, mark_dirty=False)
        self._mark_dirty()

    def __str__(self) -> str:
        """Render keyword line.

        Clean parse-backed instances preserve their verbatim source text.
        Dirty instances are rendered from semantic fields.
        """
        if not self.dirty and self._node is not None:
            return self.source_text
        rendered_value = str(self._value)
        if rendered_value == "":
            return f"#+{self._key}:\n"
        return f"#+{self._key}: {rendered_value}\n"

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"Keyword(key={self._key!r}, value={self._value!r})"
