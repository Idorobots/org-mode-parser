"""Implementation of [org_parser.text.RichText][] and inline object parsing.

`RichText` stores a sequence of inline object abstractions while preserving the
ability to emit the verbatim source slice from the parse tree until mutation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._lang import PARSER
from org_parser._node import is_error_node, node_source
from org_parser._nodes import (
    ANGLE_LINK,
    BOLD,
    CITATION,
    CODE,
    COMPLETION_COUNTER,
    ENTITY,
    EXPORT_SNIPPET,
    FOOTNOTE_REFERENCE,
    INLINE_BABEL_CALL,
    INLINE_HEADERS,
    INLINE_SOURCE_BLOCK,
    ITALIC,
    LINE_BREAK,
    MACRO,
    PARAGRAPH,
    PLAIN_LINK,
    PLAIN_TEXT,
    RADIO_TARGET,
    REGULAR_LINK,
    STRIKE_THROUGH,
    SUBSCRIPT,
    SUPERSCRIPT,
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
    InlineBabelCall,
    InlineEntity,
    InlineObject,
    InlineSourceBlock,
    Italic,
    LineBreak,
    Macro,
    PlainLink,
    PlainText,
    RadioTarget,
    RegularLink,
    StrikeThrough,
    Subscript,
    Superscript,
    Target,
    Underline,
    Verbatim,
)
from org_parser.time import Timestamp

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

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

    Example:
    ```python
    >>> from org_parser.text import RichText
    >>> text = RichText.from_source("Use *bold* text")
    >>> text.parts[1].raw
    '*bold*'
    ```
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
        """Inline object parts in source order.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> text = RichText.from_source("Use *bold* text")
        >>> len(text.parts)
        4
        ```
        """
        return self._parts

    @property
    def text(self) -> str:
        """Textual representation of this rich text.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> text = RichText.from_source("Use *bold* text")
        >>> text.text
        'Use *bold* text'
        >>> text.text = "updated"
        >>> text.text
        'updated'
        ```
        """
        return str(self)

    @text.setter
    def text(self, value: str) -> None:
        """Replace content with plain text."""
        self._parts = [PlainText(value)]
        self.mark_dirty()

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

    def mark_dirty(self) -> None:
        """Mark this rich text as dirty."""
        if self._dirty:
            return
        self._dirty = True
        parent = self._parent
        if parent is None:
            return
        parent.mark_dirty()

    def reformat(self) -> None:
        """Mark nested inline objects, then this rich text, as dirty."""
        for part in self._parts:
            part.reformat()
        self.mark_dirty()

    def append(self, part: InlineObject | str) -> None:
        """Append content.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> text = RichText("A")
        >>> text.append("B")
        >>> text.text
        'AB'
        ```
        """
        self._parts.append(_coerce_inline_object(part))
        self.mark_dirty()

    def prepend(self, part: InlineObject | str) -> None:
        """Prepend content.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> text = RichText("B")
        >>> text.prepend("A")
        >>> text.text
        'AB'
        ```
        """
        self._parts.insert(0, _coerce_inline_object(part))
        self.mark_dirty()

    def insert(self, index: int, part: InlineObject | str) -> None:
        """Insert content at *index*.

        Example:
        ```python
        >>> from org_parser.text import RichText, PlainText
        >>> text = RichText("AC")
        >>> text.insert(0, "B")
        >>> text.text
        'BAC'
        ```
        """
        self._parts.insert(index, _coerce_inline_object(part))
        self.mark_dirty()

    # -- factory methods -----------------------------------------------------

    @classmethod
    def from_source(cls, source: str) -> RichText:
        """Parse *source* and return one strict [org_parser.text.RichText][] value.

        The source must parse to exactly one paragraph element and no headings
        or zeroth-section metadata.

        Args:
            source: Org source text containing one rich-text paragraph.

        Returns:
            Parsed [org_parser.text.RichText][] for the paragraph content.

        Raises:
            ValueError: If parsing fails or the structure is not one paragraph.
        """
        from org_parser._from_source import parse_source_with_extractor

        rich_text, _ = parse_source_with_extractor(
            source,
            extractor=_extract_single_rich_text_node,
        )
        return rich_text

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        *,
        document: Document,
        parent: Document | Heading | Element | None = None,
    ) -> RichText:
        """Create a [org_parser.text.RichText][] from a single tree-sitter node.

        Args:
            node: The tree-sitter node to parse.
            document: The owning [org_parser.document.Document][].
            parent: Optional parent owner object.
        """
        if node.type == PARAGRAPH:
            parts = _parse_inline_nodes(node.named_children, document)
        else:
            parts = _parse_inline_nodes([node], document)
        rt = cls(parts, parent=parent)
        rt._document = document
        rt._source = document.source_for(node)
        return rt

    @classmethod
    def from_nodes(
        cls,
        nodes: Sequence[tree_sitter.Node],
        *,
        document: Document,
        parent: Document | Heading | Element | None = None,
    ) -> RichText:
        """Create a [org_parser.text.RichText][] from multiple contiguous nodes.

        Args:
            nodes: Ordered sequence of tree-sitter nodes to parse.
            document: The owning [org_parser.document.Document][].
            parent: Optional parent owner object.
        """
        parts = _parse_inline_nodes(nodes, document)
        rt = cls(parts, parent=parent)
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

    def __iter__(self) -> Iterator[InlineObject]:
        """Iterate over inline-object parts."""
        return iter(self._parts)

    def __len__(self) -> int:
        """Return number of inline-object parts."""
        return len(self._parts)

    def __getitem__(self, index: int | slice) -> InlineObject | list[InlineObject]:
        """Return one inline-object part (or part slice)."""
        return self._parts[index]


def _coerce_inline_object(part: InlineObject | str) -> InlineObject:
    """Convert plain strings to [org_parser.text.PlainText][] inline objects."""
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
        document: The owning [org_parser.document.Document][].
    """
    return [_parse_inline_node(node, document) for node in nodes]


def _parse_inline_node(  # noqa: PLR0911,PLR0912,PLR0915
    node: tree_sitter.Node,
    document: Document,
) -> InlineObject:
    """Parse one tree-sitter inline node into an inline object abstraction.

    Args:
        node: A single inline tree-sitter node.
        document: The owning [org_parser.document.Document][].
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
        return Bold(body=_parse_inline_nodes(node.children_by_field_name("body"), document))

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
        definition = _parse_inline_nodes(definition_nodes, document) if definition_nodes else None
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

    if node_type == MACRO:
        name_node = node.child_by_field_name("name")
        args_node = node.child_by_field_name("arguments")
        # args_node is the macro_arguments child; None when the macro has no
        # argument list (either {{{name}}} or {{{name()}}}).  We distinguish
        # the two via grammar structure: an empty () produces no macro_arguments
        # child, so both cases yield arguments=None here, which is correct —
        # the user-visible API does not distinguish them.
        return Macro(
            name=node_source(name_node, document),
            arguments=node_source(args_node, document) if args_node is not None else None,
        )

    if node_type == INLINE_BABEL_CALL:
        name_node = node.child_by_field_name("name")
        args_node = node.child_by_field_name("arguments")
        inside_node = node.child_by_field_name("inside_header")
        outside_node = node.child_by_field_name("outside_header")
        return InlineBabelCall(
            name=node_source(name_node, document),
            arguments=node_source(args_node, document) if args_node is not None else None,
            inside_header=node_source(inside_node, document) if inside_node is not None else None,
            outside_header=node_source(outside_node, document)
            if outside_node is not None
            else None,
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
            _parse_inline_nodes(description_nodes, document) if description_nodes else None
        )
        return RegularLink(path=node_source(path_node, document), description=description)

    if node_type == TARGET:
        value_node = node.child_by_field_name("value")
        return Target(value=node_source(value_node, document))

    if node_type == RADIO_TARGET:
        body_nodes = node.children_by_field_name("body")
        return RadioTarget(body=_parse_inline_nodes(body_nodes, document))

    if node_type == TIMESTAMP:
        return Timestamp.from_node(node, document)

    if node_type == SUBSCRIPT:
        source_text = document.source_for(node).decode()
        if source_text.startswith("_*"):
            return Subscript(body=[PlainText("*")], form="*")
        if source_text.startswith("_{") and source_text.endswith("}"):
            return Subscript(body=_parse_inline_fragment(source_text[2:-1]), form="{}")
        if source_text.startswith("_(") and source_text.endswith(")"):
            return Subscript(body=_parse_inline_fragment(source_text[2:-1]), form="()")
        return PlainText(source_text)

    if node_type == SUPERSCRIPT:
        source_text = document.source_for(node).decode()
        if source_text.startswith("^*"):
            return Superscript(body=[PlainText("*")], form="*")
        if source_text.startswith("^{") and source_text.endswith("}"):
            return Superscript(body=_parse_inline_fragment(source_text[2:-1]), form="{}")
        if source_text.startswith("^(") and source_text.endswith(")"):
            return Superscript(body=_parse_inline_fragment(source_text[2:-1]), form="()")
        return PlainText(source_text)

    if node_type == ENTITY:
        source_text = document.source_for(node).decode()
        if source_text.startswith("\\_"):
            # Non-breaking-space form: \_<spaces>
            return InlineEntity(name="_")
        has_braces = source_text.endswith("{}")
        name = source_text[1:-2] if has_braces else source_text[1:]
        return InlineEntity(
            name=name,
            has_braces=has_braces,
        )

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


def _parse_inline_fragment(fragment: str) -> list[InlineObject]:
    """Parse an inline fragment string into inline objects.

    Args:
        fragment: Fragment text that may contain inline Org objects.

    Returns:
        Parsed inline objects for *fragment*.
    """
    if fragment == "":
        return []

    from org_parser.document._document import Document

    source = f"{fragment}\n".encode()
    tree = PARSER.parse(source)
    parsed_document = Document.from_tree(tree, "", source)
    paragraph = _find_first_node_by_type(tree.root_node, PARAGRAPH)
    if paragraph is None:
        return [PlainText(fragment)]

    parts = _parse_inline_nodes(paragraph.named_children, parsed_document)
    if parts and isinstance(parts[-1], PlainText) and parts[-1].text == "\n":
        return parts[:-1]
    return parts


def _find_first_node_by_type(
    root: tree_sitter.Node,
    node_type: str,
) -> tree_sitter.Node | None:
    """Find the first node in *root* with matching type.

    Args:
        root: Root tree-sitter node to search.
        node_type: Target node type to locate.

    Returns:
        First matching node, or ``None`` when no such node exists.
    """
    stack: list[tree_sitter.Node] = [root]
    while stack:
        node = stack.pop()
        if node.type == node_type:
            return node
        stack.extend(reversed(node.children))
    return None


def _extract_single_rich_text_node(
    document: Document,
) -> RichText | None:
    """Return the sole rich-text semantic value for ``from_source``."""
    from org_parser.element import Paragraph

    invalid_document_shape = (
        document.keywords
        or document.properties is not None
        or document.logbook is not None
        or document.children
        or len(document.body) != 1
    )
    if invalid_document_shape:
        return None

    paragraph = document.body[0]
    if not isinstance(paragraph, Paragraph):
        return None
    return paragraph.body
