"""Implementation of :class:`RichText` and inline object parsing.

`RichText` stores a sequence of inline object abstractions while preserving the
ability to emit the verbatim source slice from the parse tree until mutation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import is_error_node, node_source
from org_parser._nodes import (
    ANGLE_LINK,
    BOLD,
    CITATION,
    CODE,
    COMPLETION_COUNTER,
    EXPORT_SNIPPET,
    FOOTNOTE_REFERENCE,
    INLINE_HEADERS,
    INLINE_SOURCE_BLOCK,
    ITALIC,
    LINE_BREAK,
    PARAGRAPH,
    PLAIN_LINK,
    PLAIN_TEXT,
    RADIO_TARGET,
    REGULAR_LINK,
    STRIKE_THROUGH,
    TARGET,
    TIMESTAMP,
    UNDERLINE,
    VERBATIM,
)
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
        self._document: Document | None = None
        self._source: bytes | None = None
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
        """Set the parent object without changing dirty state."""
        self._parent = value

    def _mark_dirty(self) -> None:
        """Mark this rich text dirty and bubble to parent objects."""
        if self._dirty:
            return
        self._dirty = True
        parent = self._parent
        if parent is None:
            return
        parent.mark_dirty()

    def mark_dirty(self) -> None:
        """Mark this rich text as dirty."""
        self._mark_dirty()

    def reformat(self) -> None:
        """Mark nested inline objects, then this rich text, as dirty."""
        for part in self._parts:
            part.reformat()
        self.mark_dirty()

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
    def from_node(
        cls,
        node: tree_sitter.Node,
        *,
        document: Document,
    ) -> RichText:
        """Create a :class:`RichText` from a single tree-sitter node.

        Args:
            node: The tree-sitter node to parse.
            document: The owning :class:`Document`.
        """
        if node.type == PARAGRAPH:
            parts = _parse_inline_nodes(node.named_children, document)
        else:
            parts = _parse_inline_nodes([node], document)
        rt = cls(parts)
        rt._document = document
        rt._source = document.source_for(node)
        return rt

    @classmethod
    def from_nodes(
        cls,
        nodes: Sequence[tree_sitter.Node],
        *,
        document: Document,
    ) -> RichText | None:
        """Create a :class:`RichText` from multiple contiguous nodes.

        Args:
            nodes: Ordered sequence of tree-sitter nodes to parse.
            document: The owning :class:`Document`.
        """
        parts = _parse_inline_nodes(nodes, document)
        rt = cls(parts)
        rt._document = document
        rt._source = b"".join(document.source_for(node) for node in nodes)
        return rt

    # -- dunder protocols ----------------------------------------------------

    def __str__(self) -> str:
        """Return rich text as Org syntax."""
        if not self._dirty and self._source is not None:
            return self._source.decode()
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
    document: Document,
) -> list[InlineObject]:
    """Parse a sequence of tree-sitter nodes into inline object abstractions.

    Args:
        nodes: Ordered sequence of tree-sitter inline nodes.
        document: The owning :class:`Document`.
    """
    return [_parse_inline_node(node, document) for node in nodes]


def _parse_inline_node(  # noqa: PLR0911,PLR0912,PLR0915
    node: tree_sitter.Node,
    document: Document,
) -> InlineObject:
    """Parse one tree-sitter inline node into an inline object abstraction.

    Args:
        node: A single inline tree-sitter node.
        document: The owning :class:`Document`.
    """
    node_type = node.type
    text = document.source_for(node).decode()

    if node_type == PLAIN_TEXT:
        return PlainText(text)

    if node_type == LINE_BREAK:
        trailing = text[2:] if text.startswith("\\\\") else ""
        return LineBreak(trailing=trailing)

    if node_type == COMPLETION_COUNTER:
        value_node = node.child_by_field_name("value")
        return CompletionCounter(node_source(value_node, document))

    if node_type == BOLD:
        return Bold(
            body=_parse_inline_nodes(node.children_by_field_name("body"), document)
        )

    if node_type == ITALIC:
        return Italic(
            body=_parse_inline_nodes(node.children_by_field_name("body"), document),
        )

    if node_type == UNDERLINE:
        return Underline(
            body=_parse_inline_nodes(node.children_by_field_name("body"), document),
        )

    if node_type == STRIKE_THROUGH:
        return StrikeThrough(
            body=_parse_inline_nodes(node.children_by_field_name("body"), document),
        )

    if node_type == VERBATIM:
        body_node = node.child_by_field_name("body")
        return Verbatim(body=node_source(body_node, document))

    if node_type == CODE:
        body_node = node.child_by_field_name("body")
        return Code(body=node_source(body_node, document))

    if node_type == EXPORT_SNIPPET:
        backend_node = node.child_by_field_name("backend")
        value_node = node.child_by_field_name("value")
        value = node_source(value_node, document) if value_node is not None else None
        return ExportSnippet(backend=node_source(backend_node, document), value=value)

    if node_type == FOOTNOTE_REFERENCE:
        label_node = node.child_by_field_name("label")
        definition_nodes = node.children_by_field_name("definition")
        definition = (
            _parse_inline_nodes(definition_nodes, document)
            if definition_nodes
            else None
        )
        label = node_source(label_node, document) if label_node is not None else None
        return FootnoteReference(label=label, definition=definition)

    if node_type == CITATION:
        style = _extract_citation_style(text)
        body_node = node.child_by_field_name("body")
        body = node_source(body_node, document) if body_node is not None else None
        return Citation(body=body, style=style)

    if node_type == INLINE_SOURCE_BLOCK:
        language_node = node.child_by_field_name("language")
        headers_nodes = node.children_by_field_name("headers")
        headers = None
        for candidate in headers_nodes:
            if candidate.type == INLINE_HEADERS:
                headers = node_source(candidate, document)
                break
        body_node = node.child_by_field_name("body")
        body = node_source(body_node, document) if body_node is not None else None
        return InlineSourceBlock(
            language=node_source(language_node, document),
            headers=headers,
            body=body,
        )

    if node_type == PLAIN_LINK:
        link_type_node = node.child_by_field_name("type")
        path_node = node.child_by_field_name("path")
        return PlainLink(
            link_type=node_source(link_type_node, document),
            path=node_source(path_node, document),
        )

    if node_type == ANGLE_LINK:
        link_type_node = node.child_by_field_name("type")
        path_node = node.child_by_field_name("path")
        link_type = node_source(link_type_node, document) if link_type_node else None
        return AngleLink(path=node_source(path_node, document), link_type=link_type)

    if node_type == REGULAR_LINK:
        path_node = node.child_by_field_name("path")
        description_nodes = node.children_by_field_name("description")
        description = (
            _parse_inline_nodes(description_nodes, document)
            if description_nodes
            else None
        )
        return RegularLink(
            path=node_source(path_node, document), description=description
        )

    if node_type == TARGET:
        value_node = node.child_by_field_name("value")
        return Target(value=node_source(value_node, document))

    if node_type == RADIO_TARGET:
        body_nodes = node.children_by_field_name("body")
        return RadioTarget(body=_parse_inline_nodes(body_nodes, document))

    if node_type == TIMESTAMP:
        return Timestamp.from_node(node, document)

    # Any remaining node that the grammar could not parse cleanly falls back to
    # PlainText.  Error and missing nodes are additionally reported so the
    # owning Document can accumulate them.
    if is_error_node(node):
        document.report_error(node)
    return PlainText(text)


def _extract_citation_style(text: str) -> str | None:
    """Extract citation style from citation text, if present."""
    if not text.startswith("[cite"):
        return None
    prefix, _, _ = text.partition(":")
    if not prefix.startswith("[cite/"):
        return None
    return prefix[len("[cite/") :]
