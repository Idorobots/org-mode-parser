"""Implementation of :class:`RichText` and inline object parsing.

`RichText` stores a sequence of inline object abstractions while preserving the
ability to emit the verbatim source slice from the parse tree until mutation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.text._inline import (
    AngleLink,
    Bold,
    Citation,
    Code,
    CompletionCounter,
    ExportSnippet,
    FootnoteReference,
    InlineObject,
    InlineSourceBlock,
    Italic,
    LineBreak,
    PlainLink,
    PlainText,
    RadioTarget,
    RegularLink,
    StrikeThrough,
    Target,
    Underline,
    Verbatim,
)
from org_parser.time import Timestamp

if TYPE_CHECKING:
    from collections.abc import Sequence

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading
    from org_parser.element._element import Element

__all__ = ["RichText"]


_BOLD = "bold"
_ITALIC = "italic"
_UNDERLINE = "underline"
_STRIKE = "strike_through"
_VERBATIM = "verbatim"
_CODE = "code"
_PLAIN_TEXT = "plain_text"
_LINE_BREAK = "line_break"
_EXPORT_SNIPPET = "export_snippet"
_FOOTNOTE_REFERENCE = "footnote_reference"
_CITATION = "citation"
_INLINE_SOURCE_BLOCK = "inline_source_block"
_PLAIN_LINK = "plain_link"
_ANGLE_LINK = "angle_link"
_REGULAR_LINK = "regular_link"
_TARGET = "target"
_RADIO_TARGET = "radio_target"
_TIMESTAMP = "timestamp"
_COMPLETION_COUNTER = "completion_counter"


class RichText:
    """Rich text content represented as Org inline objects.

    The instance remains parse-tree-backed until mutated. While clean, string
    conversion yields the exact verbatim source range from the original parse
    input. Once mutated, rendering is reconstructed from the cached object
    sequence.

    Args:
        text_or_parts: Initial content as a plain string or an explicit list of
            inline object abstractions.
    """

    def __init__(
        self,
        text_or_parts: str | list[InlineObject] = "",
        *,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        if isinstance(text_or_parts, str):
            self._parts: list[InlineObject] = [PlainText(text_or_parts)]
        else:
            self._parts = list(text_or_parts)
        self._parent = parent
        self._node: tree_sitter.Node | None = None
        self._source: bytes = b""
        self._start_byte: int | None = None
        self._end_byte: int | None = None
        self._dirty = False

    @property
    def parts(self) -> list[InlineObject]:
        """Inline object parts in source order."""
        return self._parts

    @property
    def text(self) -> str:
        """Textual representation of this rich text."""
        return str(self)

    @text.setter
    def text(self, value: str) -> None:
        """Replace content with plain text and mark rich text as dirty."""
        self._parts = [PlainText(value)]
        self._mark_dirty()

    @property
    def dirty(self) -> bool:
        """Whether this rich text has been mutated after creation."""
        return self._dirty

    @property
    def parent(self) -> Document | Heading | Element | None:
        """Parent object that contains this rich text, if any."""
        return self._parent

    @parent.setter
    def parent(self, value: Document | Heading | Element | None) -> None:
        """Set the parent object and mark rich text as dirty."""
        self.set_parent(value)

    def set_parent(
        self,
        value: Document | Heading | Element | None,
        *,
        mark_dirty: bool = True,
    ) -> None:
        """Set parent object with optional dirty propagation."""
        self._parent = value
        if mark_dirty:
            self._mark_dirty()

    def _mark_dirty(self) -> None:
        """Mark this rich text dirty and bubble to parent objects."""
        if self._dirty:
            return
        self._dirty = True
        parent = self._parent
        if parent is None:
            return
        dirty_parent = parent
        if not dirty_parent.dirty:
            dirty_parent.mark_dirty()

    def mark_dirty(self) -> None:
        """Mark this rich text as dirty."""
        self._mark_dirty()

    def append(self, part: InlineObject | str) -> None:
        """Append content and mark rich text as dirty."""
        self._parts.append(_coerce_inline_object(part))
        self._mark_dirty()

    def prepend(self, part: InlineObject | str) -> None:
        """Prepend content and mark rich text as dirty."""
        self._parts.insert(0, _coerce_inline_object(part))
        self._mark_dirty()

    def insert(self, index: int, part: InlineObject | str) -> None:
        """Insert content at *index* and mark rich text as dirty."""
        self._parts.insert(index, _coerce_inline_object(part))
        self._mark_dirty()

    # -- factory methods -----------------------------------------------------

    @classmethod
    def from_node(cls, node: tree_sitter.Node, source: bytes) -> RichText:
        """Create a :class:`RichText` from a single tree-sitter node."""
        if node.type == "paragraph":
            parts = _parse_inline_nodes(node.named_children, source)
        else:
            parts = _parse_inline_nodes([node], source)
        rt = cls(parts)
        rt._node = node
        rt._source = source
        rt._start_byte = node.start_byte
        rt._end_byte = node.end_byte
        return rt

    @classmethod
    def from_nodes(
        cls,
        nodes: Sequence[tree_sitter.Node],
        source: bytes,
    ) -> RichText | None:
        """Create a :class:`RichText` from multiple contiguous nodes."""
        if not nodes:
            return None
        first = nodes[0]
        last = nodes[-1]
        parts = _parse_inline_nodes(nodes, source)
        rt = cls(parts)
        rt._node = first
        rt._source = source
        rt._start_byte = first.start_byte
        rt._end_byte = last.end_byte
        return rt

    # -- dunder protocols ----------------------------------------------------

    def __str__(self) -> str:
        """Return rich text as Org syntax."""
        if (
            not self._dirty
            and self._start_byte is not None
            and self._end_byte is not None
            and self._source
        ):
            return self._source[self._start_byte : self._end_byte].decode()
        return "".join(str(part) for part in self._parts)

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"RichText({str(self)!r})"

    def __eq__(self, other: object) -> bool:
        """Compare by rendered textual content."""
        if isinstance(other, RichText):
            return str(self) == str(other)
        if isinstance(other, str):
            return str(self) == other
        return NotImplemented

    def __hash__(self) -> int:
        """Hash by rendered textual content."""
        return hash(str(self))


def _coerce_inline_object(part: InlineObject | str) -> InlineObject:
    """Convert plain strings to :class:`PlainText` inline objects."""
    if isinstance(part, str):
        return PlainText(part)
    return part


def _parse_inline_nodes(
    nodes: Sequence[tree_sitter.Node],
    source: bytes,
) -> list[InlineObject]:
    """Parse a sequence of tree-sitter nodes into inline object abstractions."""
    return [_parse_inline_node(node, source) for node in nodes]


def _parse_inline_node(  # noqa: PLR0911,PLR0912,PLR0915
    node: tree_sitter.Node,
    source: bytes,
) -> InlineObject:
    """Parse one tree-sitter inline node into an inline object abstraction."""
    node_type = node.type
    text = _node_text(node, source)

    if node_type == _PLAIN_TEXT:
        return PlainText(text)

    if node_type == _LINE_BREAK:
        trailing = text[2:] if text.startswith("\\\\") else ""
        return LineBreak(trailing=trailing)

    if node_type == _COMPLETION_COUNTER:
        value_node = node.child_by_field_name("value")
        return CompletionCounter(_safe_node_text(value_node, source))

    if node_type == _BOLD:
        return Bold(
            body=_parse_inline_nodes(node.children_by_field_name("body"), source)
        )

    if node_type == _ITALIC:
        return Italic(
            body=_parse_inline_nodes(node.children_by_field_name("body"), source),
        )

    if node_type == _UNDERLINE:
        return Underline(
            body=_parse_inline_nodes(node.children_by_field_name("body"), source),
        )

    if node_type == _STRIKE:
        return StrikeThrough(
            body=_parse_inline_nodes(node.children_by_field_name("body"), source),
        )

    if node_type == _VERBATIM:
        body_node = node.child_by_field_name("body")
        return Verbatim(body=_safe_node_text(body_node, source))

    if node_type == _CODE:
        body_node = node.child_by_field_name("body")
        return Code(body=_safe_node_text(body_node, source))

    if node_type == _EXPORT_SNIPPET:
        backend_node = node.child_by_field_name("backend")
        value_node = node.child_by_field_name("value")
        value = _safe_node_text(value_node, source) if value_node is not None else None
        return ExportSnippet(backend=_safe_node_text(backend_node, source), value=value)

    if node_type == _FOOTNOTE_REFERENCE:
        label_node = node.child_by_field_name("label")
        definition_nodes = node.children_by_field_name("definition")
        definition = (
            _parse_inline_nodes(definition_nodes, source) if definition_nodes else None
        )
        label = _safe_node_text(label_node, source) if label_node is not None else None
        return FootnoteReference(label=label, definition=definition)

    if node_type == _CITATION:
        style = _extract_citation_style(text)
        body_node = node.child_by_field_name("body")
        body = _safe_node_text(body_node, source) if body_node is not None else None
        return Citation(body=body, style=style)

    if node_type == _INLINE_SOURCE_BLOCK:
        language_node = node.child_by_field_name("language")
        headers_nodes = node.children_by_field_name("headers")
        headers = None
        for candidate in headers_nodes:
            if candidate.type == "inline_headers":
                headers = _node_text(candidate, source)
                break
        body_node = node.child_by_field_name("body")
        body = _safe_node_text(body_node, source) if body_node is not None else None
        return InlineSourceBlock(
            language=_safe_node_text(language_node, source),
            headers=headers,
            body=body,
        )

    if node_type == _PLAIN_LINK:
        link_type_node = node.child_by_field_name("type")
        path_node = node.child_by_field_name("path")
        return PlainLink(
            link_type=_safe_node_text(link_type_node, source),
            path=_safe_node_text(path_node, source),
        )

    if node_type == _ANGLE_LINK:
        link_type_node = node.child_by_field_name("type")
        path_node = node.child_by_field_name("path")
        link_type = _safe_node_text(link_type_node, source) if link_type_node else None
        return AngleLink(path=_safe_node_text(path_node, source), link_type=link_type)

    if node_type == _REGULAR_LINK:
        path_node = node.child_by_field_name("path")
        description_nodes = node.children_by_field_name("description")
        description = (
            _parse_inline_nodes(description_nodes, source)
            if description_nodes
            else None
        )
        return RegularLink(
            path=_safe_node_text(path_node, source), description=description
        )

    if node_type == _TARGET:
        value_node = node.child_by_field_name("value")
        return Target(value=_safe_node_text(value_node, source))

    if node_type == _RADIO_TARGET:
        body_nodes = node.children_by_field_name("body")
        return RadioTarget(body=_parse_inline_nodes(body_nodes, source))

    if node_type == _TIMESTAMP:
        return Timestamp.from_node(node, source)

    return PlainText(text)


def _extract_citation_style(text: str) -> str | None:
    """Extract citation style from citation text, if present."""
    if not text.startswith("[cite"):
        return None
    prefix, _, _ = text.partition(":")
    if not prefix.startswith("[cite/"):
        return None
    return prefix[len("[cite/") :]


def _safe_node_text(node: tree_sitter.Node | None, source: bytes) -> str:
    """Return node text or an empty string for missing nodes."""
    if node is None:
        return ""
    return _node_text(node, source)


def _node_text(node: tree_sitter.Node, source: bytes) -> str:
    """Return source text covered by one node."""
    return source[node.start_byte : node.end_byte].decode()
