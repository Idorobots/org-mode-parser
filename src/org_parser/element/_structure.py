"""Structural body element classes for Org section nodes.

This module covers elements that govern the physical structure of a section
body but carry no textual content of their own:

* [org_parser.element.BlankLine][] — an empty separator line (``blank_line`` node).
* [org_parser.element.Comment][] — a single-line ``#`` comment.
* [org_parser.element.HorizontalRule][] — a ``-----`` horizontal rule line.
* [org_parser.element.Indent][] — a contiguous indented chunk (``indent`` node).
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
    from collections.abc import Callable, Iterator, Sequence

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = [
    "BlankLine",
    "Comment",
    "HorizontalRule",
    "Indent",
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
        """Create a [org_parser.element.BlankLine][] from a ``blank_line`` node."""
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

    Example:
    ```python
    >>> from org_parser import loads
    >>> document = loads("# comment")
    >>> document.body[0].text
    'comment'
    ```
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
        """Create a [org_parser.element.Comment][] from a ``comment`` node."""
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
        """Set comment body text."""
        self._text = value
        self.mark_dirty()

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
        """Create a [org_parser.element.HorizontalRule][] from a ``horizontal_rule`` node."""
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
        """Set the rule text."""
        self._rule = value
        self.mark_dirty()

    def __str__(self) -> str:
        """Render the rule line, preserving source while parse-backed and clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        return f"{self._rule}\n"

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("HorizontalRule", rule=self._rule)


class Indent(Element):
    """Indentation wrapper node with nested body elements.

    Grammar ``indent`` nodes represent one contiguous indented chunk.
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

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
        child_factory: Callable[..., Element],
    ) -> Indent:
        """Build one [org_parser.element.Indent][] from a tree-sitter ``indent`` node.

        The *child_factory* callable is responsible for dispatching each named
        ``body`` field child to the appropriate element constructor for the
        current parsing context.  It must accept the positional arguments
        ``(node, document)`` and the keyword argument ``parent``.

        Args:
            node: A tree-sitter ``indent`` node.
            document: The owning
                [org_parser.document.Document][].
            parent: Optional parent element to assign to the returned block.
            child_factory: Callable with signature
                ``(child_node, document, *, parent) -> Element`` used to build
                each named body child.

        Returns:
            An [org_parser.element.Indent][] whose body elements are built by
            *child_factory* and whose source span is attached for clean
            round-trip rendering.
        """
        indent_node = node.child_by_field_name("indent")
        indent_text = node_source(indent_node, document)
        indent = indent_text if indent_text != "" else None
        block = cls(
            body=[
                child_factory(child, document, parent=parent)
                for child in node.children_by_field_name("body")
                if child.is_named
            ],
            indent=indent,
        )
        block.attach_source(node, document)
        return block

    @property
    def indent(self) -> str | None:
        """Leading indentation for this block's first line, if known."""
        return self._indent

    @indent.setter
    def indent(self, value: str | None) -> None:
        """Set block indentation text."""
        self._indent = value
        self.mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Nested elements contained by this indentation block."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set nested elements."""
        self._body = value
        self._adopt_body(self._body)
        self.mark_dirty()

    @property
    def body_text(self) -> str:
        """Stringified text of all nested indentation-block elements."""
        return "".join(str(element) for element in self._body)

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
        return build_semantic_repr("Indent", body=self._body, indent=self._indent)

    def __iter__(self) -> Iterator[Element]:
        """Iterate over body elements."""
        return iter(self._body)

    def __len__(self) -> int:
        """Return number of body elements."""
        return len(self._body)

    def __getitem__(self, index: int | slice) -> Element | list[Element]:
        """Return one body element (or body slice)."""
        return self._body[index]
