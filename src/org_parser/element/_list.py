"""Semantic element classes for Org plain lists and list items."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from org_parser._node import is_error_node, node_source
from org_parser._nodes import INDENT, LIST_ITEM
from org_parser.element._dispatch import body_element_factories
from org_parser.element._element import (
    Element,
    build_semantic_repr,
    element_from_error_or_unknown,
    ensure_trailing_newline,
)
from org_parser.element._structure import Indent
from org_parser.text._inline import LineBreak, PlainText
from org_parser.text._rich_text import RichText
from org_parser.time import Timestamp

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["List", "ListItem", "Repeat"]


_REPEAT_HEADER_PREFIX_PATTERN = re.compile(
    r'^State\s+"(?P<after>[^"]+)"\s+from\s+"(?P<before>[^"]+)"\s+$'
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
    ) -> None:
        super().__init__(parent=parent)
        self._bullet = bullet
        self._ordered_counter = ordered_counter
        self._counter_set = counter_set
        self._checkbox = checkbox
        self._item_tag = item_tag
        self._first_line = first_line
        self._body = body if body is not None else []

        if self._item_tag is not None:
            self._item_tag.parent = self
        if self._first_line is not None:
            self._first_line.parent = self
        self._adopt_body(self._body)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> ListItem:
        """Create one :class:`ListItem` from a ``list_item`` parse node."""
        item = cls(
            bullet=_extract_bullet(node, document),
            ordered_counter=_extract_optional_field_text(node, document, "counter"),
            counter_set=_extract_counter_set(node, document),
            checkbox=_extract_checkbox(node, document),
            item_tag=_extract_item_tag(node, document),
            first_line=_extract_first_line(node, document),
            body=[
                _extract_list_body_element(child, document, parent=None)
                for child in node.children_by_field_name("body")
                if child.is_named
            ],
            parent=parent,
        )
        item._node = node
        item._document = document
        return item

    @property
    def bullet(self) -> str:
        """Bullet marker (``-``, ``+``, ``*``, ``.``, or ``)``)."""
        return self._bullet

    @bullet.setter
    def bullet(self, value: str) -> None:
        """Set bullet marker and mark item dirty."""
        self._bullet = value
        self.mark_dirty()

    @property
    def ordered_counter(self) -> str | None:
        """Ordered-list counter value for numeric/alpha bullets."""
        return self._ordered_counter

    @ordered_counter.setter
    def ordered_counter(self, value: str | None) -> None:
        """Set ordered-list counter value and mark item dirty."""
        self._ordered_counter = value
        self.mark_dirty()

    @property
    def counter_set(self) -> str | None:
        """Counter-set cookie value without wrapper syntax."""
        return self._counter_set

    @counter_set.setter
    def counter_set(self, value: str | None) -> None:
        """Set counter-set cookie value and mark item dirty."""
        self._counter_set = value
        self.mark_dirty()

    @property
    def checkbox(self) -> str | None:
        """Checkbox status character: ``" "``, ``"X"``, ``"-"``, or ``None``."""
        return self._checkbox

    @checkbox.setter
    def checkbox(self, value: str | None) -> None:
        """Set checkbox status and mark item dirty."""
        self._checkbox = value
        self.mark_dirty()

    @property
    def item_tag(self) -> RichText | None:
        """Descriptive-list tag rich text before ``::`` when present."""
        return self._item_tag

    @item_tag.setter
    def item_tag(self, value: RichText | None) -> None:
        """Set item tag and mark item dirty."""
        self._item_tag = value
        if self._item_tag is not None:
            self._item_tag.parent = self
        self.mark_dirty()

    @property
    def first_line(self) -> RichText | None:
        """First-line rich text after bullet metadata."""
        return self._first_line

    @first_line.setter
    def first_line(self, value: RichText | None) -> None:
        """Set first-line rich text and mark item dirty."""
        self._first_line = value
        if self._first_line is not None:
            self._first_line.parent = self
        self.mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Mutable body elements for this list item."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set body elements and mark item dirty."""
        self._body = value
        self._adopt_body(self._body)
        self.mark_dirty()

    @property
    def body_text(self) -> str:
        """Stringified text of all list body elements."""
        return "".join(str(element) for element in self._body)

    def append_body(self, element: Element, *, mark_dirty: bool = True) -> None:
        """Append one body element with optional dirty propagation."""
        element.parent = self
        self._body.append(element)
        if mark_dirty:
            self.mark_dirty()

    def reformat(self) -> None:
        """Mark all child content and this item dirty."""
        if self._item_tag is not None:
            self._item_tag.reformat()
        if self._first_line is not None:
            self._first_line.reformat()
        for element in self._body:
            element.reformat()
        self.mark_dirty()

    def _adopt_body(self, body: Sequence[Element]) -> None:
        """Assign this item as parent for all body elements."""
        for element in body:
            element.parent = self

    def __str__(self) -> str:
        """Render list-item text from semantic fields when dirty."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)

        return self._render_dirty()

    def _render_dirty(self, *, indent_step: int = 2) -> str:
        """Render list-item text from semantic fields for dirty output."""
        parts: list[str] = []

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
        body_prefix = " " * indent_step
        for element in self._body:
            rendered = ensure_trailing_newline(str(element))
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

    def __iter__(self) -> Iterator[Element]:
        """Iterate over body elements."""
        return iter(self._body)

    def __len__(self) -> int:
        """Return number of body elements."""
        return len(self._body)

    def __getitem__(self, index: int | slice) -> Element | list[Element]:
        """Return one body element (or body slice)."""
        return self._body[index]


class Repeat(ListItem):
    """Repeated-task logbook entry represented as a specialized list item."""

    state_alignment_space = 12

    def __init__(
        self,
        *,
        after: str,
        before: str,
        timestamp: Timestamp,
        body: list[Element] | None = None,
        bullet: str = "-",
        ordered_counter: str | None = None,
        counter_set: str | None = None,
        item_tag: RichText | None = None,
        first_line: RichText | None = None,
        checkbox: str | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(
            bullet=bullet,
            ordered_counter=ordered_counter,
            counter_set=counter_set,
            checkbox=checkbox,
            item_tag=item_tag,
            first_line=first_line,
            body=body,
            parent=parent,
        )
        self._after = after
        self._before = before
        self._timestamp = timestamp

    @classmethod
    def from_list_item(cls, item: ListItem, document: Document) -> Repeat | None:
        """Build a :class:`Repeat` from one list item when pattern-matched."""
        if (
            item.item_tag is not None
            or item.counter_set is not None
            or item.checkbox is not None
            or item.ordered_counter is not None
            or item.first_line is None
        ):
            return None

        parsed = _parse_repeat_first_line(item.first_line)
        if parsed is None:
            return None
        after, before, timestamp, has_remainder = parsed

        if has_remainder:
            if item._node is not None:
                # NOTE These are considered malformed.
                document.report_error(item._node)
            return None

        body = list(item.body)

        repeat = cls(
            after=after,
            before=before,
            timestamp=timestamp,
            body=body,
            bullet=item.bullet,
            item_tag=item.item_tag,
            first_line=item.first_line,
            ordered_counter=item.ordered_counter,
            counter_set=item.counter_set,
            checkbox=item.checkbox,
            parent=item.parent,
        )
        repeat._node = item._node
        repeat._document = item._document
        return repeat

    @property
    def after(self) -> str:
        """Task state after the repeat transition."""
        return self._after

    @after.setter
    def after(self, value: str) -> None:
        """Set the after-state and mark repeat entry dirty."""
        self._after = value
        self.mark_dirty()

    @property
    def before(self) -> str:
        """Task state before the repeat transition."""
        return self._before

    @before.setter
    def before(self, value: str) -> None:
        """Set the before-state and mark repeat entry dirty."""
        self._before = value
        self.mark_dirty()

    @property
    def timestamp(self) -> Timestamp:
        """Timestamp recorded for the repeat transition."""
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value: Timestamp) -> None:
        """Set repeat timestamp and mark repeat entry dirty."""
        self._timestamp = value
        self.mark_dirty()

    def reformat(self) -> None:
        """Mark timestamp, any child content, and this entry dirty."""
        self._timestamp.reformat()
        if self._item_tag is not None:
            self._item_tag.reformat()
        if self._first_line is not None:
            self._first_line.reformat()
        for element in self._body:
            element.reformat()
        self.mark_dirty()

    def __str__(self) -> str:
        """Render repeat entry preserving source text while clean."""
        if not self.dirty:
            return super().__str__()
        return self._render_dirty()

    def _render_dirty(self, *, indent_step: int = 2) -> str:
        """Render repeat entry text from semantic fields for dirty output."""
        parts: list[str] = []
        if self._ordered_counter is not None and self._bullet in {".", ")"}:
            parts.append(f"{self._ordered_counter}{self._bullet} ")
        else:
            parts.append(f"{self._bullet} ")
        if self._counter_set is not None:
            parts.append(f"[@{self._counter_set}] ")
        if self._checkbox is not None:
            parts.append(f"[{self._checkbox}] ")
        after = f'"{self._after}"'
        before = f'"{self._before}"'
        parts.append(
            f"State {after:<{self.state_alignment_space}}"
            f" from {before:<{self.state_alignment_space}} {self._timestamp}"
        )
        if self._body:
            parts.append(" \\\\\n")
            body_prefix = " " * indent_step
            for element in self._body:
                rendered = ensure_trailing_newline(str(element))
                parts.append(_indent_non_empty_lines(rendered, body_prefix))
        else:
            parts.append("\n")
        return "".join(parts)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr(
            "Repeat",
            after=self._after,
            before=self._before,
            timestamp=self._timestamp,
            body=self._body,
        )


class List(Element):
    """Plain list element containing mutable :class:`ListItem` instances."""

    def __init__(
        self,
        *,
        items: list[ListItem] | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._items = items if items is not None else []
        self._adopt_items(self._items)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> List:
        """Create a :class:`List` from a ``list`` node."""
        items = [
            ListItem.from_node(child, document, parent=None)
            for child in node.named_children
            if child.type == LIST_ITEM
        ]
        parsed = cls(items=items, parent=parent)
        parsed._node = node
        parsed._document = document
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
            self.mark_dirty()

    def append_item(self, item: ListItem, *, mark_dirty: bool = True) -> None:
        """Append one list item with optional dirty propagation."""
        item.parent = self
        self._items.append(item)
        if mark_dirty:
            self.mark_dirty()

    def insert_item(self, index: int, item: ListItem) -> None:
        """Insert one list item at *index* and mark list dirty."""
        item.parent = self
        self._items.insert(index, item)
        self.mark_dirty()

    def reformat(self) -> None:
        """Mark all items and this list dirty."""
        for item in self._items:
            item.reformat()
        self.mark_dirty()

    def _adopt_items(self, items: Sequence[ListItem]) -> None:
        """Assign this list as parent for all items."""
        for item in items:
            item.parent = self

    def mark_dirty(self) -> None:
        """Mark this list and all direct items as dirty."""
        if self._dirty:
            return
        self._dirty = True
        for item in self._items:
            item._dirty = True
        parent = self._parent
        if parent is None:
            return
        parent.mark_dirty()

    def __str__(self) -> str:
        """Render list text preserving source while clean and parse-backed."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        return "".join(str(item) for item in self._items)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("List", items=self._items)

    def __iter__(self) -> Iterator[ListItem]:
        """Iterate over list items."""
        return iter(self._items)

    def __len__(self) -> int:
        """Return number of list items."""
        return len(self._items)

    def __getitem__(self, index: int | slice) -> ListItem | list[ListItem]:
        """Return one list item (or list-item slice)."""
        return self._items[index]


def _extract_optional_field_text(
    node: tree_sitter.Node,
    document: Document,
    field_name: str,
) -> str | None:
    """Return one optional field's text, or ``None`` when absent."""
    field_node = node.child_by_field_name(field_name)
    if field_node is None:
        return None
    value = document.source_for(field_node).decode()
    return value if value != "" else None


def _extract_bullet(node: tree_sitter.Node, document: Document) -> str:
    """Return bullet marker text from one list item node.

    For unordered items the ``unordered_bullet`` token includes trailing
    whitespace (e.g. ``"- "``), so the value is right-stripped to return
    just the marker character (``"-"``, ``"+"``, or ``"*"``).  For ordered
    items the terminator token (``"."`` or ``")"``) has no trailing
    whitespace and is returned as-is.
    """
    bullet_nodes = node.children_by_field_name("bullet")
    if not bullet_nodes:
        return "-"
    bullet_node = bullet_nodes[-1]
    value = document.source_for(bullet_node).decode()
    return value.rstrip() if value else "-"


def _extract_counter_set(
    node: tree_sitter.Node,
    document: Document,
) -> str | None:
    """Return counter-set value from ``[@n]`` syntax without wrappers."""
    counter_set = _extract_optional_field_text(node, document, "counter_set")
    if counter_set is None:
        return None
    stripped = counter_set.strip()
    if stripped.startswith("[@") and stripped.endswith("]"):
        value = stripped[2:-1].strip()
        return value if value != "" else None
    return stripped if stripped != "" else None


def _extract_checkbox(node: tree_sitter.Node, document: Document) -> str | None:
    """Return checkbox status character from one list item node."""
    checkbox_node = node.child_by_field_name("checkbox")
    if checkbox_node is None:
        return None
    status_node = checkbox_node.child_by_field_name("status")
    if status_node is None:
        return None
    value = document.source_for(status_node).decode()
    return value or None


def _extract_item_tag(
    node: tree_sitter.Node,
    document: Document,
) -> RichText | None:
    """Return descriptive-list tag rich text, if present."""
    tag_node = node.child_by_field_name("tag")
    if tag_node is None:
        return None
    return RichText.from_nodes(tag_node.named_children, document=document)


def _extract_first_line(
    node: tree_sitter.Node,
    document: Document,
) -> RichText | None:
    """Return first-line rich text composed from all ``first_line`` objects."""
    return RichText.from_nodes(
        node.children_by_field_name("first_line"), document=document
    )


def _indent_non_empty_lines(value: str, prefix: str) -> str:
    """Prefix each non-empty line in *value* with *prefix*."""
    if prefix == "":
        return value
    lines = value.splitlines(keepends=True)
    return "".join(f"{prefix}{line}" if line.strip() != "" else line for line in lines)


def _parse_repeat_first_line(
    first_line: RichText,
) -> tuple[str, str, Timestamp, bool] | None:
    """Parse one repeat header from a list item's first-line text.

    Returns:
        A tuple of ``(after, before, timestamp, has_remainder)``
        when the line matches repeat syntax, otherwise ``None``.
    """
    if len(first_line.parts) < 2:
        return None

    prefix_part = first_line.parts[0]
    timestamp_part = first_line.parts[1]

    if not isinstance(prefix_part, PlainText) or not isinstance(
        timestamp_part, Timestamp
    ):
        return None

    matched = _REPEAT_HEADER_PREFIX_PATTERN.match(prefix_part.text)
    if matched is None:
        return None

    has_remainder = False
    if len(first_line.parts) > 2 and not isinstance(first_line.parts[-1], LineBreak):
        has_remainder = True

    return (
        matched.group("after"),
        matched.group("before"),
        timestamp_part,
        has_remainder,
    )


def _normalize_optional_text(value: str | None) -> str | None:
    """Return stripped text value, or ``None`` when empty."""
    if value is None:
        return None
    normalized = value.strip()
    if normalized == "":
        return None
    return normalized


def _extract_list_body_element(
    node: tree_sitter.Node,
    document: Document,
    *,
    parent: Document | Heading | Element | None = None,
) -> Element:
    """Build one semantic element object for a list-item body child node."""
    if is_error_node(node):
        return element_from_error_or_unknown(node, document, parent=parent)
    if node.type == INDENT:
        return _extract_indent(node, document, parent=parent)

    dispatch: dict[str, Callable[..., Element]] = body_element_factories()
    factory = dispatch.get(node.type)
    if factory is None:
        return element_from_error_or_unknown(node, document, parent=parent)
    return factory(node, document, parent=parent)


def _extract_indent(
    node: tree_sitter.Node,
    document: Document,
    *,
    parent: Document | Heading | Element | None = None,
) -> Indent:
    """Build one :class:`Indent` for a list-item body ``indent`` node."""
    return Indent.from_node(
        node, document, parent=parent, child_factory=_extract_list_body_element
    )
