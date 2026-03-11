"""Semantic element classes for Org plain lists and list items."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import TYPE_CHECKING

from org_parser.element._element import Element, build_semantic_repr
from org_parser.text._rich_text import RichText
from org_parser.time import Timestamp

if TYPE_CHECKING:
    from collections.abc import Sequence

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["List", "ListItem", "ListItemContinuation", "Repeat"]


_REPEAT_PATTERN = re.compile(
    r'^State\s+"(?P<after>[^"]+)"\s+from\s+"(?P<before>[^"]+)"\s+'
    r"(?P<timestamp><[^>\n]+>|\[[^\]\n]+\](?:--\[[^\]\n]+\])?)"
    r"(?:\s*(?P<line_break>\\\\)?(?:\n(?P<note_line>.*))?)?$",
    re.DOTALL,
)


class ListItemContinuation(Element):
    """Indented continuation line that belongs to one list item."""

    def __init__(
        self,
        *,
        content: RichText,
        line_prefix: str = "",
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(
            node_type="item_continuation_line",
            source_text=source_text,
            parent=parent,
        )
        self._line_prefix = line_prefix
        self._content = content
        self._content.set_parent(self, mark_dirty=False)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        source: bytes,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> ListItemContinuation:
        """Create a continuation line from one ``item_continuation_line`` node."""
        source_text = source[node.start_byte : node.end_byte].decode()
        content_nodes = node.children_by_field_name("content")
        parsed = RichText.from_nodes(content_nodes, source)
        continuation = cls(
            content=RichText("") if parsed is None else parsed,
            line_prefix=_extract_leading_indent(source_text),
            parent=parent,
            source_text=source_text,
        )
        continuation._node = node
        return continuation

    @property
    def content(self) -> RichText:
        """Mutable continuation rich-text content."""
        return self._content

    @content.setter
    def content(self, value: RichText) -> None:
        """Set continuation content and mark continuation as dirty."""
        self._content = value
        self._content.set_parent(self, mark_dirty=False)
        self._mark_dirty()

    def __str__(self) -> str:
        """Render continuation line text."""
        if not self.dirty and self._node is not None:
            return self.source_text
        return f"{self._line_prefix}{self._content}\n"

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr(
            "ListItemContinuation",
            content=self._content,
        )


class ListItem(Element):
    """One mutable plain-list item with all item-level metadata."""

    def __init__(
        self,
        *,
        bullet: str,
        ordered_counter: str | None = None,
        counter_set: str | None = None,
        checkbox: str | None = None,
        item_tag: RichText | None = None,
        first_line: RichText | None = None,
        body: list[Element] | None = None,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(node_type="list_item", source_text=source_text, parent=parent)
        self._line_prefix = _extract_leading_indent(source_text)
        self._bullet = bullet
        self._ordered_counter = ordered_counter
        self._counter_set = counter_set
        self._checkbox = checkbox
        self._item_tag = item_tag
        self._first_line = first_line
        self._body = body if body is not None else []

        if self._item_tag is not None:
            self._item_tag.set_parent(self, mark_dirty=False)
        if self._first_line is not None:
            self._first_line.set_parent(self, mark_dirty=False)
        self._adopt_body(self._body)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        source: bytes,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> ListItem:
        """Create one :class:`ListItem` from a ``list_item`` parse node."""
        source_text = source[node.start_byte : node.end_byte].decode()
        item = cls(
            bullet=_extract_bullet(node, source),
            ordered_counter=_extract_optional_field_text(node, source, "counter"),
            counter_set=_extract_counter_set(node, source),
            checkbox=_extract_checkbox(node, source),
            item_tag=_extract_item_tag(node, source),
            first_line=_extract_first_line(node, source),
            body=[
                _extract_list_item_body_element(child, source)
                for child in node.children_by_field_name("body")
            ],
            parent=parent,
            source_text=source_text,
        )
        item._node = node
        return item

    @property
    def bullet(self) -> str:
        """Bullet marker (``-``, ``+``, ``*``, ``.``, or ``)``)."""
        return self._bullet

    @bullet.setter
    def bullet(self, value: str) -> None:
        """Set bullet marker and mark item dirty."""
        self._bullet = value
        self._mark_dirty()

    @property
    def ordered_counter(self) -> str | None:
        """Ordered-list counter value for numeric/alpha bullets."""
        return self._ordered_counter

    @ordered_counter.setter
    def ordered_counter(self, value: str | None) -> None:
        """Set ordered-list counter value and mark item dirty."""
        self._ordered_counter = value
        self._mark_dirty()

    @property
    def counter_set(self) -> str | None:
        """Counter-set cookie value without wrapper syntax."""
        return self._counter_set

    @counter_set.setter
    def counter_set(self, value: str | None) -> None:
        """Set counter-set cookie value and mark item dirty."""
        self._counter_set = value
        self._mark_dirty()

    @property
    def checkbox(self) -> str | None:
        """Checkbox status character: ``" "``, ``"X"``, ``"-"``, or ``None``."""
        return self._checkbox

    @checkbox.setter
    def checkbox(self, value: str | None) -> None:
        """Set checkbox status and mark item dirty."""
        self._checkbox = value
        self._mark_dirty()

    @property
    def item_tag(self) -> RichText | None:
        """Descriptive-list tag rich text before ``::`` when present."""
        return self._item_tag

    @item_tag.setter
    def item_tag(self, value: RichText | None) -> None:
        """Set item tag and mark item dirty."""
        self._item_tag = value
        if self._item_tag is not None:
            self._item_tag.set_parent(self, mark_dirty=False)
        self._mark_dirty()

    @property
    def first_line(self) -> RichText | None:
        """First-line rich text after bullet metadata."""
        return self._first_line

    @first_line.setter
    def first_line(self, value: RichText | None) -> None:
        """Set first-line rich text and mark item dirty."""
        self._first_line = value
        if self._first_line is not None:
            self._first_line.set_parent(self, mark_dirty=False)
        self._mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Mutable body elements for this list item."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set body elements and mark item dirty."""
        self._body = value
        self._adopt_body(self._body)
        self._mark_dirty()

    def append_body(self, element: Element, *, mark_dirty: bool = True) -> None:
        """Append one body element with optional dirty propagation."""
        element.set_parent(self, mark_dirty=False)
        self._body.append(element)
        if mark_dirty:
            self._mark_dirty()

    def _adopt_body(self, body: Sequence[Element]) -> None:
        """Assign this item as parent for all body elements."""
        for element in body:
            element.set_parent(self, mark_dirty=False)

    def __str__(self) -> str:
        """Render list-item text from semantic fields when dirty."""
        if not self.dirty and self._node is not None and not self._body:
            return self.source_text

        default_indent = self._line_prefix if self._line_prefix != "" else None
        return self.render_with_indent(default_indent)

    def render_with_indent(self, indent: str | None, *, indent_step: int = 2) -> str:
        """Render list-item text with one explicit indentation prefix."""
        parts: list[str] = []
        if indent is not None:
            parts.append(indent)

        if self._ordered_counter is not None and self._bullet in {".", ")"}:
            parts.append(f"{self._ordered_counter}{self._bullet} ")
        else:
            parts.append(f"{self._bullet} ")

        if self._counter_set is not None:
            parts.append(f"[@{self._counter_set}] ")

        if self._checkbox is not None:
            parts.append(f"[{self._checkbox}] ")

        if self._item_tag is not None:
            parts.append(f"{self._item_tag} ::")
        elif self._first_line is not None:
            parts.append(str(self._first_line))

        parts.append("\n")
        body_prefix = (indent if indent is not None else "") + (" " * indent_step)
        for element in self._body:
            rendered = _ensure_trailing_newline(str(element))
            if element.node_type == "plain_list":
                parts.append(rendered)
                continue
            parts.append(_indent_non_empty_lines(rendered, body_prefix))
        return "".join(parts)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr(
            "ListItem",
            bullet=self._bullet,
            counter_set=self._counter_set,
            checkbox=self._checkbox,
            item_tag=self._item_tag,
            first_line=self._first_line,
            body=self._body,
        )


class Repeat(ListItem):
    """Repeated-task logbook entry represented as a specialized list item."""

    def __init__(
        self,
        *,
        after: str,
        before: str,
        timestamp: Timestamp,
        note: str | None = None,
        note_indent: str | None = None,
        bullet: str = "-",
        ordered_counter: str | None = None,
        counter_set: str | None = None,
        checkbox: str | None = None,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(
            bullet=bullet,
            ordered_counter=ordered_counter,
            counter_set=counter_set,
            checkbox=checkbox,
            item_tag=None,
            first_line=None,
            body=[],
            parent=parent,
            source_text=source_text,
        )
        self._node_type = "repeat"
        self._after = after
        self._before = before
        self._timestamp = timestamp
        self._note = _normalize_optional_text(note)
        indent = _extract_leading_indent(source_text)
        normalized_indent = indent if indent != "" else None
        self._note_indent = (
            note_indent
            if note_indent is not None
            else _default_note_indent(normalized_indent)
        )

    @classmethod
    def from_list_item(cls, item: ListItem) -> Repeat | None:
        """Build a :class:`Repeat` from one list item when pattern-matched."""
        matched = _parse_repeat_source(item.source_text)
        if matched is None:
            return None
        repeat = cls(
            after=matched.after,
            before=matched.before,
            timestamp=matched.timestamp,
            note=matched.note,
            note_indent=matched.note_indent,
            bullet=item.bullet,
            ordered_counter=item.ordered_counter,
            counter_set=item.counter_set,
            checkbox=item.checkbox,
            parent=item.parent,
            source_text=item.source_text,
        )
        repeat._node = item._node
        return repeat

    @property
    def after(self) -> str:
        """Task state after the repeat transition."""
        return self._after

    @after.setter
    def after(self, value: str) -> None:
        """Set the after-state and mark repeat entry dirty."""
        self._after = value
        self._mark_dirty()

    @property
    def before(self) -> str:
        """Task state before the repeat transition."""
        return self._before

    @before.setter
    def before(self, value: str) -> None:
        """Set the before-state and mark repeat entry dirty."""
        self._before = value
        self._mark_dirty()

    @property
    def timestamp(self) -> Timestamp:
        """Timestamp recorded for the repeat transition."""
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value: Timestamp) -> None:
        """Set repeat timestamp and mark repeat entry dirty."""
        self._timestamp = value
        self._mark_dirty()

    @property
    def note(self) -> str | None:
        """Optional short note from continuation line, if present."""
        return self._note

    @note.setter
    def note(self, value: str | None) -> None:
        """Set optional note text and mark repeat entry dirty."""
        self._note = _normalize_optional_text(value)
        self._mark_dirty()

    def __str__(self) -> str:
        """Render repeat entry preserving source text while clean."""
        if not self.dirty and self._node is not None:
            return self.source_text

        default_indent = self._line_prefix if self._line_prefix != "" else None
        return self.render_with_indent(default_indent)

    def render_with_indent(self, indent: str | None, *, indent_step: int = 2) -> str:
        """Render repeat entry text with one explicit indentation prefix."""
        parts: list[str] = []
        if indent is not None:
            parts.append(indent)
        if self._ordered_counter is not None and self._bullet in {".", ")"}:
            parts.append(f"{self._ordered_counter}{self._bullet} ")
        else:
            parts.append(f"{self._bullet} ")
        if self._counter_set is not None:
            parts.append(f"[@{self._counter_set}] ")
        if self._checkbox is not None:
            parts.append(f"[{self._checkbox}] ")
        parts.append(f'State "{self._after}" from "{self._before}" {self._timestamp}')
        if self._note is None:
            parts.append("\n")
            return "".join(parts)
        parts.append(" \\\\\n")
        parts.append(f"{self._note_indent}{self._note}\n")
        return "".join(parts)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr(
            "Repeat",
            after=self._after,
            before=self._before,
            timestamp=self._timestamp,
            note=self._note,
            body=self._body,
        )


class List(Element):
    """Plain list element containing mutable :class:`ListItem` instances."""

    default_indent_step = 2

    def __init__(
        self,
        *,
        items: list[ListItem] | None = None,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(node_type="plain_list", source_text=source_text, parent=parent)
        self._items = items if items is not None else []
        self._adopt_items(self._items)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        source: bytes,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> List:
        """Create a :class:`List` from a ``plain_list`` node."""
        items = [
            ListItem.from_node(child, source)
            for child in node.named_children
            if child.type == "list_item"
        ]
        parsed = cls(
            items=items,
            parent=parent,
            source_text=source[node.start_byte : node.end_byte].decode(),
        )
        parsed._node = node
        return parsed

    @property
    def items(self) -> list[ListItem]:
        """Mutable list items in source order."""
        return self._items

    @items.setter
    def items(self, value: list[ListItem]) -> None:
        """Set list items and mark list dirty."""
        self.set_items(value)

    def set_items(self, value: list[ListItem], *, mark_dirty: bool = True) -> None:
        """Set list items with optional dirty propagation."""
        self._items = value
        self._adopt_items(self._items)
        if mark_dirty:
            self._mark_dirty()

    def append_item(self, item: ListItem, *, mark_dirty: bool = True) -> None:
        """Append one list item with optional dirty propagation."""
        item.set_parent(self, mark_dirty=False)
        self._items.append(item)
        if mark_dirty:
            self._mark_dirty()

    def insert_item(self, index: int, item: ListItem) -> None:
        """Insert one list item at *index* and mark list dirty."""
        item.set_parent(self, mark_dirty=False)
        self._items.insert(index, item)
        self._mark_dirty()

    def _adopt_items(self, items: Sequence[ListItem]) -> None:
        """Assign this list as parent for all items."""
        for item in items:
            item.set_parent(self, mark_dirty=False)

    def _mark_dirty(self) -> None:
        """Mark this list and all direct items as dirty."""
        if self._dirty:
            return
        self._dirty = True
        for item in self._items:
            item._dirty = True
        parent = self._parent
        if parent is None:
            return
        if not parent.dirty:
            parent.mark_dirty()

    def __str__(self) -> str:
        """Render list text preserving source while clean and parse-backed."""
        if not self.dirty and self._node is not None:
            return self.source_text
        depth = _list_depth(self)
        indent = " " * (depth * self.default_indent_step)
        return "".join(
            item.render_with_indent(indent, indent_step=self.default_indent_step)
            for item in self._items
        )

    @classmethod
    def set_default_indent_step(cls, value: int) -> None:
        """Set class-wide indentation width for dirty list rendering."""
        if value < 0:
            raise ValueError("List indentation step must be non-negative")
        cls.default_indent_step = value

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("List", items=self._items)


def _extract_list_item_body_element(node: tree_sitter.Node, source: bytes) -> Element:
    """Build one semantic element for a list item's body child node."""
    from org_parser.element._block import (
        CenterBlock,
        CommentBlock,
        DynamicBlock,
        ExampleBlock,
        ExportBlock,
        FixedWidthBlock,
        QuoteBlock,
        SourceBlock,
        SpecialBlock,
        VerseBlock,
    )
    from org_parser.element._drawer import Drawer, Logbook, Properties

    dispatch = {
        "item_continuation_line": ListItemContinuation.from_node,
        "drawer": Drawer.from_node,
        "logbook_drawer": Logbook.from_node,
        "property_drawer": Properties.from_node,
        "fixed_width": FixedWidthBlock.from_node,
        "center_block": CenterBlock.from_node,
        "quote_block": QuoteBlock.from_node,
        "special_block": SpecialBlock.from_node,
        "dynamic_block": DynamicBlock.from_node,
        "comment_block": CommentBlock.from_node,
        "example_block": ExampleBlock.from_node,
        "export_block": ExportBlock.from_node,
        "src_block": SourceBlock.from_node,
        "verse_block": VerseBlock.from_node,
    }
    factory = dispatch.get(node.type)
    if factory is None:
        return Element.from_node(node, source)
    return factory(node, source)


def _extract_optional_field_text(
    node: tree_sitter.Node,
    source: bytes,
    field_name: str,
) -> str | None:
    """Return one optional field's text, or ``None`` when absent."""
    field_node = node.child_by_field_name(field_name)
    if field_node is None:
        return None
    value = source[field_node.start_byte : field_node.end_byte].decode()
    return value if value != "" else None


def _extract_bullet(node: tree_sitter.Node, source: bytes) -> str:
    """Return bullet marker text from one list item node."""
    bullet_nodes = node.children_by_field_name("bullet")
    if not bullet_nodes:
        return "-"
    bullet_node = bullet_nodes[-1]
    return source[bullet_node.start_byte : bullet_node.end_byte].decode()


def _extract_counter_set(node: tree_sitter.Node, source: bytes) -> str | None:
    """Return counter-set value from ``[@n]`` syntax without wrappers."""
    counter_set = _extract_optional_field_text(node, source, "counter_set")
    if counter_set is None:
        return None
    stripped = counter_set.strip()
    if stripped.startswith("[@") and stripped.endswith("]"):
        value = stripped[2:-1].strip()
        return value if value != "" else None
    return stripped if stripped != "" else None


def _extract_checkbox(node: tree_sitter.Node, source: bytes) -> str | None:
    """Return checkbox status character from one list item node."""
    checkbox_node = node.child_by_field_name("checkbox")
    if checkbox_node is None:
        return None
    status_node = checkbox_node.child_by_field_name("status")
    if status_node is None:
        return None
    return source[status_node.start_byte : status_node.end_byte].decode()


def _extract_item_tag(node: tree_sitter.Node, source: bytes) -> RichText | None:
    """Return descriptive-list tag rich text, if present."""
    tag_node = node.child_by_field_name("tag")
    if tag_node is None:
        return None
    return RichText.from_nodes(tag_node.named_children, source)


def _extract_first_line(node: tree_sitter.Node, source: bytes) -> RichText | None:
    """Return first-line rich text composed from all ``first_line`` objects."""
    return RichText.from_nodes(node.children_by_field_name("first_line"), source)


def _extract_leading_indent(value: str) -> str:
    """Return leading indentation from one line of source text."""
    indent_end = 0
    while indent_end < len(value) and value[indent_end] in {" ", "\t"}:
        indent_end += 1
    return value[:indent_end]


def _ensure_trailing_newline(value: str) -> str:
    """Return *value* with one trailing newline when non-empty."""
    if value == "" or value.endswith("\n"):
        return value
    return f"{value}\n"


def _indent_non_empty_lines(value: str, prefix: str) -> str:
    """Prefix each non-empty line in *value* with *prefix*."""
    if prefix == "":
        return value
    lines = value.splitlines(keepends=True)
    return "".join(f"{prefix}{line}" if line.strip() != "" else line for line in lines)


def _list_depth(list_node: List) -> int:
    """Return nesting depth by walking list ancestors."""
    depth = 0
    parent = list_node.parent
    while parent is not None:
        if isinstance(parent, ListItem):
            grandparent = parent.parent
            if isinstance(grandparent, List):
                depth += 1
                parent = grandparent.parent
                continue
        parent = parent.parent if isinstance(parent, Element) else None
    return depth


@dataclass(slots=True)
class _RepeatMatch:
    """Parsed repeated-task fields extracted from one list item text."""

    after: str
    before: str
    timestamp: Timestamp
    note: str | None
    note_indent: str


def _parse_repeat_source(source_text: str) -> _RepeatMatch | None:
    """Parse one repeated-task list item and return extracted fields."""
    body = _strip_item_prefix(source_text.rstrip("\n"))
    if body is None:
        return None
    body = body.replace("\\\\n", "\n")

    matched = _REPEAT_PATTERN.match(body)
    if matched is None:
        return None

    timestamp_text = matched.group("timestamp")
    note_line = matched.group("note_line")
    note_indent = _extract_leading_indent(note_line) if note_line is not None else ""
    note = None if note_line is None else note_line.strip()

    return _RepeatMatch(
        after=matched.group("after"),
        before=matched.group("before"),
        timestamp=_parse_timestamp_text(timestamp_text),
        note=_normalize_optional_text(note),
        note_indent=note_indent,
    )


def _strip_item_prefix(source_text: str) -> str | None:
    """Strip leading list marker prefix from one list-item source text."""
    line, separator, rest = source_text.partition("\n")
    prefix_match = re.match(r"^[ \t]*(?:[-+*]|[0-9]+[.)]|[a-z][.)])[ \t]+", line)
    if prefix_match is None:
        return None
    remainder = line[prefix_match.end() :]
    return remainder if separator == "" else f"{remainder}\n{rest}"


def _parse_timestamp_text(raw: str) -> Timestamp:
    """Parse one timestamp string into :class:`Timestamp`."""
    from org_parser._lang import PARSER

    source = f"{raw}\n".encode()
    root = PARSER.parse(source).root_node
    timestamp_node = _find_first_timestamp_node(root)
    if timestamp_node is None:
        raise ValueError(f"Could not parse repeat timestamp: {raw!r}")
    return Timestamp.from_node(timestamp_node, source)


def _find_first_timestamp_node(node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Return first ``timestamp`` descendant node in source order."""
    if node.type == "timestamp":
        return node
    for child in node.named_children:
        matched = _find_first_timestamp_node(child)
        if matched is not None:
            return matched
    return None


def _normalize_optional_text(value: str | None) -> str | None:
    """Return stripped text value, or ``None`` when empty."""
    if value is None:
        return None
    normalized = value.strip()
    if normalized == "":
        return None
    return normalized


def _default_note_indent(indent: str | None) -> str:
    """Return default continuation indentation for repeat note lines."""
    base = "" if indent is None else indent
    return f"{base}  "
