"""Structural body element classes for Org section nodes.

This module covers elements that govern the physical structure of a section
body but carry no textual content of their own:

* :class:`BlankLine` — an empty separator line (``blank_line`` node).
* :class:`Comment` — a single-line ``#`` comment.
* :class:`HorizontalRule` — a ``-----`` horizontal rule line.
* :class:`IndentBlock` — a contiguous indented chunk (``block`` node).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import node_source
from org_parser.element._element import (
    Element,
    build_semantic_repr,
    ensure_trailing_newline,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = [
    "BlankLine",
    "Comment",
    "HorizontalRule",
    "IndentBlock",
]


class BlankLine(Element):
    """A blank separator line between body elements.

    Org Mode blank lines are structurally significant — they separate
    elements — but carry no semantic content of their own.
    """

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> BlankLine:
        """Create a :class:`BlankLine` from a ``blank_line`` node."""
        elem = cls(parent=parent)
        elem.attach_source(node, document)
        return elem

    def __str__(self) -> str:
        """Render the blank line, preserving source while parse-backed and clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        return "\n"

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return "BlankLine()"


class Comment(Element):
    """A single-line ``#`` comment.

    Args:
        text: The comment body text, excluding the leading ``#`` marker and
            optional following space.
    """

    def __init__(
        self,
        *,
        text: str,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._text = text

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Comment:
        """Create a :class:`Comment` from a ``comment`` node."""
        raw = node_source(node, document).rstrip("\n")
        if raw.startswith("# "):
            text = raw[2:]
        elif raw.startswith("#"):
            text = raw[1:]
        else:
            text = raw
        elem = cls(text=text, parent=parent)
        elem.attach_source(node, document)
        return elem

    @property
    def text(self) -> str:
        """Mutable comment body text (excluding the ``#`` prefix)."""
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        """Set comment body text and mark this element as dirty."""
        self._text = value
        self._mark_dirty()

    def __str__(self) -> str:
        """Render the comment line, preserving source while parse-backed and clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        if self._text == "":
            return "#\n"
        return f"# {self._text}\n"

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("Comment", text=self._text)


class HorizontalRule(Element):
    """A horizontal rule line (five or more dashes).

    Args:
        rule: The rule text without its trailing newline (e.g. ``"-----"``).
    """

    def __init__(
        self,
        *,
        rule: str = "-----",
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._rule = rule

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> HorizontalRule:
        """Create a :class:`HorizontalRule` from a ``horizontal_rule`` node."""
        raw = node_source(node, document).rstrip("\n")
        elem = cls(rule=raw, parent=parent)
        elem.attach_source(node, document)
        return elem

    @property
    def rule(self) -> str:
        """Mutable rule text without the trailing newline."""
        return self._rule

    @rule.setter
    def rule(self, value: str) -> None:
        """Set the rule text and mark this element as dirty."""
        self._rule = value
        self._mark_dirty()

    def __str__(self) -> str:
        """Render the rule line, preserving source while parse-backed and clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        return f"{self._rule}\n"

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("HorizontalRule", rule=self._rule)


class IndentBlock(Element):
    """Indentation wrapper node with nested body elements.

    Grammar ``block`` nodes represent one contiguous indented chunk.
    """

    def __init__(
        self,
        *,
        body: list[Element] | None = None,
        indent: str | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._body = body if body is not None else []
        self._indent = indent
        self._adopt_body(self._body)

    @property
    def indent(self) -> str | None:
        """Leading indentation for this block's first line, if known."""
        return self._indent

    @indent.setter
    def indent(self, value: str | None) -> None:
        """Set block indentation text and mark this block as dirty."""
        self._indent = value
        self._mark_dirty()

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
            element.parent = self

    def reformat(self) -> None:
        """Mark body and this block dirty for scratch-built rendering."""
        for element in self._body:
            element.reformat()
        self.mark_dirty()

    def __str__(self) -> str:
        """Render indentation block text.

        Clean parse-backed instances preserve their verbatim source text.
        Dirty instances join their body elements.
        """
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        return "".join(ensure_trailing_newline(str(element)) for element in self._body)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("IndentBlock", body=self._body, indent=self._indent)
