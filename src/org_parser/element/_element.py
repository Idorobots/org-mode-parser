"""Base class for Org Mode structural element nodes.

An [org_parser.element.Element][] wraps a tree-sitter node that represents an Org Mode
*greater element* or *lesser element* (paragraph, plain list, source block,
drawer, etc.).  Concrete subclasses add per-element semantic fields;
[org_parser.element.Element][] itself should not be instantiated directly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, TypeVar, cast

from org_parser._node import node_source
from org_parser.element._dirty_list import DirtyList

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading
    from org_parser.element._keyword import AffiliatedKeyword

__all__ = ["DirtyList", "Element", "node_source"]

_ElementT = TypeVar("_ElementT", bound="Element")


def build_semantic_repr(class_name: str, /, **fields: object) -> str:
    """Build a semantic repr omitting ``None`` and empty-list fields.

    The representation stays compact for leaf values and automatically switches
    to a multiline format when a field contains nested semantic structure.
    """
    normalized_fields: dict[str, object] = dict(fields)
    visible_fields: list[tuple[str, object]] = []
    for name, value in normalized_fields.items():
        if _is_omitted_repr_field(value):
            continue
        visible_fields.append((name, value))
    if not visible_fields:
        return f"{class_name}()"

    rendered_fields = [
        (name, _format_repr_value(value, indent_level=1)) for name, value in visible_fields
    ]
    multiline = any("\n" in rendered for _, rendered in rendered_fields)
    if not multiline:
        parts = [f"{name}={rendered}" for name, rendered in rendered_fields]
        return f"{class_name}({', '.join(parts)})"

    lines = [f"{class_name}("]
    for name, rendered in rendered_fields:
        lines.extend(_format_repr_field(name, rendered, indent_level=1))
    lines.append(")")
    return "\n".join(lines)


def _format_repr_field(name: str, rendered: str, *, indent_level: int) -> list[str]:
    """Return formatted repr lines for one named field."""
    indent = _repr_indent(indent_level)
    value_lines = rendered.splitlines()
    if len(value_lines) == 1:
        return [f"{indent}{name}={value_lines[0]},"]

    lines = [f"{indent}{name}={value_lines[0]}"]
    lines.extend(f"{indent}{line}" for line in value_lines[1:])
    lines[-1] = f"{lines[-1]},"
    return lines


def _format_repr_value(value: object, *, indent_level: int) -> str:
    """Return a repr string for *value* with nested indentation."""
    if isinstance(value, list):
        return _format_repr_sequence(
            "[",
            "]",
            cast(list[object], value),
            indent_level=indent_level,
        )
    if isinstance(value, tuple):
        return _format_repr_sequence(
            "(",
            ")",
            cast(tuple[object, ...], value),
            indent_level=indent_level,
        )
    if isinstance(value, set):
        set_value = cast(set[object], value)
        if not set_value:
            return "set()"
        ordered = sorted(set_value, key=repr)
        return _format_repr_sequence("{", "}", ordered, indent_level=indent_level)
    if isinstance(value, Mapping):
        return _format_repr_mapping(cast(Mapping[object, object], value), indent_level=indent_level)
    return repr(value)


def _format_repr_sequence(
    opening: str,
    closing: str,
    values: Sequence[object],
    *,
    indent_level: int,
) -> str:
    """Return a repr for a sequence with optional multiline expansion."""
    if not values:
        return f"{opening}{closing}"

    rendered_items = [_format_repr_value(value, indent_level=indent_level + 1) for value in values]
    multiline = any("\n" in rendered for rendered in rendered_items) or any(
        _is_semantic_object(value) for value in values
    )
    if not multiline:
        return f"{opening}{', '.join(rendered_items)}{closing}"

    inner_indent = _repr_indent(indent_level + 1)
    closing_indent = _repr_indent(indent_level)
    lines = [opening]
    for rendered in rendered_items:
        lines.extend(_indent_repr_lines(rendered, prefix=inner_indent))
        lines[-1] = f"{lines[-1]},"
    lines.append(f"{closing_indent}{closing}")
    return "\n".join(lines)


def _format_repr_mapping(
    values: Mapping[object, object],
    *,
    indent_level: int,
) -> str:
    """Return a repr for a mapping with optional multiline expansion."""
    if not values:
        return "{}"

    rendered_entries = [
        (
            repr(key),
            _format_repr_value(value, indent_level=indent_level + 1),
            key,
            value,
        )
        for key, value in values.items()
    ]
    multiline = any("\n" in rendered for _, rendered, _, _ in rendered_entries) or any(
        _is_semantic_object(key) or _is_semantic_object(value)
        for _, _, key, value in rendered_entries
    )
    if not multiline:
        compact_entries = [f"{key}: {rendered}" for key, rendered, _, _ in rendered_entries]
        return f"{{{', '.join(compact_entries)}}}"

    inner_indent = _repr_indent(indent_level + 1)
    closing_indent = _repr_indent(indent_level)
    lines = ["{"]
    for key, rendered, _, _ in rendered_entries:
        value_lines = rendered.splitlines()
        lines.append(f"{inner_indent}{key}: {value_lines[0]}")
        lines.extend(f"{inner_indent}{line}" for line in value_lines[1:])
        lines[-1] = f"{lines[-1]},"
    lines.append(f"{closing_indent}}}")
    return "\n".join(lines)


def _indent_repr_lines(rendered: str, *, prefix: str) -> list[str]:
    """Return *rendered* split into lines and prefixed by *prefix*."""
    return [f"{prefix}{line}" for line in rendered.splitlines()]


def _repr_indent(level: int) -> str:
    """Return indentation for one repr nesting *level*."""
    return "  " * level


def _is_semantic_object(value: object) -> bool:
    """Return whether *value* is one of this package's semantic objects."""
    return value.__class__.__module__.startswith("org_parser.")


def _is_omitted_repr_field(value: object) -> bool:
    """Return whether *value* should be omitted from semantic repr output."""
    return value is None or (isinstance(value, list) and not value)


class Element:
    """Base class for an Org Mode element node.

    Concrete subclasses represent specific element types (paragraph, list,
    drawer, block, etc.).  This class should not be instantiated directly.

    Args:
        parent: Optional parent object that owns this element.
    """

    def __init__(
        self,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        self._parent = parent
        self._node: tree_sitter.Node | None = None
        self._document: Document | None = None
        self._dirty = False
        self._keywords: list[AffiliatedKeyword] = []

    @classmethod
    def from_source(cls: type[_ElementT], source: str) -> _ElementT:  # noqa: PYI019
        """Parse *source* and return one strict semantic element.

        The source must parse to exactly one non-heading semantic element.

        Args:
            source: Org source text containing exactly one element.

        Returns:
            The parsed semantic element instance.

        Raises:
            ValueError: If parsing fails or structure is not exactly one element.
            TypeError: If the parsed element does not match *cls*.
        """
        from org_parser._from_source import parse_document_from_source

        document = parse_document_from_source(source)
        if document.children:
            raise ValueError("Unexpected parse tree structure")

        semantic_nodes: list[Element] = []
        semantic_nodes.extend(document.keywords)
        if len(document.properties) > 0:
            semantic_nodes.append(document.properties)
        if len(document.logbook) > 0:
            semantic_nodes.append(document.logbook)
        semantic_nodes.extend(document.body)

        if len(semantic_nodes) != 1:
            raise ValueError("Unexpected parse tree structure")

        semantic_node: Element = semantic_nodes[0]
        if not isinstance(semantic_node, cls):
            raise TypeError(
                f"Parsed element is {semantic_node.__class__.__name__}, " f"expected {cls.__name__}"
            )
        return semantic_node

    # -- public read-only properties -----------------------------------------

    @property
    def parent(self) -> Document | Heading | Element | None:
        """Parent object that contains this element, if any."""
        return self._parent

    @parent.setter
    def parent(self, value: Document | Heading | Element | None) -> None:
        """Set the parent object without changing dirty state."""
        self._parent = value

    @property
    def dirty(self) -> bool:
        """Whether this element has been mutated after creation."""
        return self._dirty

    @property
    def line(self) -> int | None:
        """Zero-based source line of this element's parse node, or *None*."""
        if self._node is None:
            return None
        return self._node.start_point.row

    @property
    def column(self) -> int | None:
        """Zero-based source column of this element's parse node, or *None*."""
        if self._node is None:
            return None
        return self._node.start_point.column

    @property
    def text(self) -> str:
        """Stringified text representation of this element."""
        return str(self)

    @property
    def body_text(self) -> str:
        """Stringified body text for elements that implement body content."""
        return ""

    @property
    def keywords(self) -> list[AffiliatedKeyword]:
        """Affiliated keywords attached to this element, in document order.

        Affiliated keywords (``#+CAPTION:``, ``#+TBLNAME:``, ``#+PLOT:``,
        ``#+RESULTS:``) that immediately precede this element in the document
        body are linked here during parsing.  The list is empty when no
        affiliated keywords precede this element.

        The keywords remain as independent elements in the containing body
        list and are not duplicated in the serialised output of this element.

        Example:
        ```python
        >>> from org_parser.element import CaptionKeyword
        >>> document = loads('''
        ... #+CAPTION: Some Table
        ... |table|
        ... ''')
        >>> document.body[0].keywords[0].value
        'Some Table'
        ```
        """

        def on_keywords_mutation(wrapped: DirtyList[AffiliatedKeyword]) -> None:
            self._keywords = list(wrapped)
            for keyword in self._keywords:
                keyword.parent = self
            self.mark_dirty()

        return DirtyList(self._keywords, on_mutation=on_keywords_mutation)

    def attach_keyword(self, keyword: AffiliatedKeyword) -> None:
        """Attach an affiliated keyword to this element without marking it dirty.

        This method is called during body post-processing to link affiliated
        keywords (``#+CAPTION:``, ``#+TBLNAME:``, ``#+PLOT:``,
        ``#+RESULTS:``) to the element that immediately follows them.  The
        keyword is appended to [org_parser.element.Element.keywords][] in document order.

        Args:
            keyword: The affiliated keyword to attach.

        Example:
        ```python
        >>> from org_parser.element import CaptionKeyword
        >>> document = loads("|table|")
        >>> c = CaptionKeyword.from_source("#+CAPTION: Some table")
        >>> document.body[0].attach_keyword(c)
        >>> len(document.body[0].keywords)
        1
        >>> print(str(document))

        >>> document.body = [c, document.body[0]]
        >>> print(str(document))
        #+CAPTION: Some table
        |table|
        ```
        """
        self._keywords = [*self._keywords, keyword]
        keyword.parent = self

    def mark_dirty(self) -> None:
        """Mark this element as dirty."""
        if self._dirty:
            return
        self._dirty = True
        parent = self._parent
        if parent is None:
            return
        parent.mark_dirty()

    def attach_source(
        self,
        node: tree_sitter.Node,
        document: Document | None,
    ) -> None:
        """Attach parse-tree source backing to this element.

        This method is for internal factory use — call it immediately after
        construction to wire up the parse-tree node and owning document.

        Args:
            node: The tree-sitter node this element was built from.
            document: The owning [org_parser.document.Document][], or *None*.
        """
        self._node = node
        self._document = document

    def reformat(self) -> None:
        """Mark this element dirty for scratch-built rendering."""
        self.mark_dirty()

    # -- dunder protocols ----------------------------------------------------

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return "Element()"


def coerce_element_body(value: Sequence[Element] | Element | str) -> list[Element]:
    """Return *value* as a mutable list of semantic elements.

    Raw strings are wrapped in a single
    [org_parser.element.Paragraph][] element.
    """
    if isinstance(value, str):
        from org_parser.element._paragraph import Paragraph

        return [Paragraph(body=value)]
    if isinstance(value, Element):
        return [value]
    if isinstance(value, list):
        return value
    return list(value)


# ---------------------------------------------------------------------------
# Shared node utilities
# ---------------------------------------------------------------------------


def element_from_error_or_unknown(
    node: tree_sitter.Node,
    document: Document | None = None,
    *,
    parent: Document | Heading | Element | None = None,
    error_message: str | None = None,
) -> Element:
    """Return a semantic element for an unrecognised or error parse node.

    All unrecognised nodes — whether a parser ``ERROR``, a missing token, or
    an unknown but syntactically valid node type — are recovered as a
    [org_parser.element.Paragraph][] whose ``body`` is a
    [org_parser.text.RichText][] of the verbatim source
    text.  The owning [org_parser.document.Document][]'s
    [org_parser.document.Document.report_error][] method is
    invoked so the document can record the error.

    Args:
        node: The unrecognised tree-sitter node.
        document: The owning [org_parser.document.Document][], or *None* for programmatic
            construction (source defaults to ``b""``).
        parent: Optional owner object.
        error_message: Optional semantic classification to pass through to
            [org_parser.document.Document.report_error][].

    Returns:
        A [org_parser.element.Paragraph][] wrapping the
        verbatim source text of *node*.
    """
    if document is not None:
        document.report_error(node, error_message)
    # Lazy imports avoid the circular dependency
    # (_paragraph imports Element; _rich_text imports time/).
    from org_parser.element._paragraph import Paragraph
    from org_parser.text._rich_text import RichText

    text = node_source(node, document)
    paragraph = Paragraph(body=RichText(text), parent=parent)
    paragraph.attach_source(node, document)
    return paragraph


def ensure_trailing_newline(value: str) -> str:
    r"""Return *value* with exactly one trailing newline when non-empty.

    Args:
        value: Any string, possibly without a trailing newline.

    Returns:
        The original string unchanged if empty or already newline-terminated;
        otherwise the string with one ``\n`` appended.
    """
    if value == "" or value.endswith("\n"):
        return value
    return f"{value}\n"
