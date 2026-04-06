"""Semantic element classes for Org plain lists and list items."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import is_error_node, node_source
from org_parser._nodes import INDENT, LIST_ITEM
from org_parser.element._dirty_list import DirtyList
from org_parser.element._dispatch import body_element_factories
from org_parser.element._element import (
    Element,
    build_semantic_repr,
    coerce_element_body,
    element_from_error_or_unknown,
    ensure_trailing_newline,
)
from org_parser.element._structure import Indent
from org_parser.text._inline import LineBreak, PlainText
from org_parser.text._rich_text import RichText, coerce_optional_rich_text
from org_parser.time import Timestamp

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["List", "ListItem", "Repeat"]


class ListItem(Element):
    r"""One mutable plain-list item with all item-level metadata.

    Example:
    ```python
    >>> from org_parser.element import ListItem
    >>> from org_parser.text import RichText
    >>> from org_parser import loads
    >>> document = loads("- Item 0\n")
    >>> document.body[0].items.append(ListItem(bullet="-", first_line=RichText("Item 1")))
    >>> document.body[0][0].checkbox = "X"
    >>> document.body[0][1].bullet = '+'
    >>> print(str(document))
    - [X] Item 0
    + Item 1
    ```
    """

    def __init__(
        self,
        *,
        bullet: str,
        ordered_counter: str | None = None,
        counter_set: str | None = None,
        checkbox: str | None = None,
        item_tag: RichText | str | None = None,
        first_line: RichText | str | None = None,
        body: Sequence[Element] = (),
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._bullet = bullet
        self._ordered_counter = ordered_counter
        self._counter_set = counter_set
        self._checkbox = checkbox
        self._item_tag = coerce_optional_rich_text(item_tag)
        self._first_line = coerce_optional_rich_text(first_line)
        self._body = list(body)

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
        """Create one [org_parser.element.ListItem][] from a ``list_item`` parse node."""
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

    @classmethod
    def from_source(cls, source: str) -> ListItem:
        """Parse *source* and return one strict [org_parser.element.ListItem][].

        The source must parse to exactly one list item wrapped by one plain
        list element and no other semantic nodes.

        Args:
            source: Org source text containing exactly one list item.

        Returns:
            Parsed [org_parser.element.ListItem][].

        Raises:
            ValueError: If parsing fails or the structure is not one list item.
        """
        from org_parser._from_source import parse_source_with_extractor

        list_item, _ = parse_source_with_extractor(
            source,
            extractor=_extract_single_list_item_node,
        )
        return list_item

    @property
    def bullet(self) -> str:
        """Bullet marker (``-``, ``+``, ``*``, ``.``, or ``)``)."""
        return self._bullet

    @bullet.setter
    def bullet(self, value: str) -> None:
        """Set bullet marker."""
        self._bullet = value
        self.mark_dirty()

    @property
    def ordered_counter(self) -> str | None:
        """Ordered-list counter value for numeric/alpha bullets."""
        return self._ordered_counter

    @ordered_counter.setter
    def ordered_counter(self, value: str | None) -> None:
        """Set ordered-list counter value."""
        self._ordered_counter = value
        self.mark_dirty()

    @property
    def counter_set(self) -> str | None:
        """Counter-set cookie value without wrapper syntax."""
        return self._counter_set

    @counter_set.setter
    def counter_set(self, value: str | None) -> None:
        """Set counter-set cookie value."""
        self._counter_set = value
        self.mark_dirty()

    @property
    def checkbox(self) -> str | None:
        """Checkbox status character: ``" "``, ``"X"``, ``"-"``, or ``None``."""
        return self._checkbox

    @checkbox.setter
    def checkbox(self, value: str | None) -> None:
        """Set checkbox status."""
        self._checkbox = value
        self.mark_dirty()

    @property
    def item_tag(self) -> RichText | None:
        """Descriptive-list tag rich text before ``::`` when present."""
        return self._item_tag

    @item_tag.setter
    def item_tag(self, value: RichText | str | None) -> None:
        """Set item tag."""
        self._item_tag = coerce_optional_rich_text(value)
        if self._item_tag is not None:
            self._item_tag.parent = self
        self.mark_dirty()

    @property
    def first_line(self) -> RichText | None:
        """First-line rich text after bullet metadata."""
        return self._first_line

    @first_line.setter
    def first_line(self, value: RichText | str | None) -> None:
        """Set first-line rich text."""
        self._first_line = coerce_optional_rich_text(value)
        if self._first_line is not None:
            self._first_line.parent = self
        self.mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Mutable body elements for this list item."""

        def on_body_mutation(wrapped: DirtyList[Element]) -> None:
            self._body = list(wrapped)
            self._adopt_body(self._body)
            self.mark_dirty()

        return DirtyList(self._body, on_mutation=on_body_mutation)

    @body.setter
    def body(self, value: Sequence[Element] | Element | str) -> None:
        """Set body elements."""
        self._body = list(coerce_element_body(value))
        self._adopt_body(self._body)
        self.mark_dirty()

    @property
    def body_text(self) -> str:
        """Stringified text of all list body elements."""
        return "".join(str(element) for element in self._body)

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
            if self._first_line is not None:
                parts.append(f" {self._first_line}")
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
            ordered_counter=self._ordered_counter,
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
    """Repeated-task logbook entry represented as a specialized list item.

    Example:
    ```python
    >>> from org_parser import loads
    >>> from org_parser.element import Repeat
    >>> from org_parser.time import Timestamp
    >>> heading = loads("* TODO Heading 1").children[0]
    >>> ts = Timestamp.from_source("<2025-10-10>")
    >>> heading.add_repeat(Repeat(after="DONE", before="TODO", timestamp=ts))
    >>> print(str(heading))
    * TODO Heading 1
    :LOGBOOK:
    - State "DONE"       from "TODO"       <2025-10-10>
    :END:
    ```
    """

    state_alignment_space = 12

    def __init__(
        self,
        *,
        after: str | None,
        before: str | None,
        timestamp: Timestamp,
        body: Sequence[Element] = (),
        bullet: str = "-",
        ordered_counter: str | None = None,
        counter_set: str | None = None,
        item_tag: RichText | str | None = None,
        first_line: RichText | str | None = None,
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
        self._timestamp.parent = self

    @classmethod
    def from_list_item(cls, item: ListItem, document: Document) -> Repeat | None:
        """Build a [org_parser.element.Repeat][] from one list item when pattern-matched."""
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
                from org_parser.document._document import invalid_repeat_message

                document.report_error(item._node, invalid_repeat_message())
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
        repeat.attach_document(document)
        return repeat

    @property
    def after(self) -> str | None:
        """Task state after the repeat transition."""
        return self._after

    @after.setter
    def after(self, value: str | None) -> None:
        """Set the after-state."""
        self._after = value
        self.mark_dirty()

    @property
    def before(self) -> str | None:
        """Task state before the repeat transition."""
        return self._before

    @before.setter
    def before(self, value: str | None) -> None:
        """Set the before-state."""
        self._before = value
        self.mark_dirty()

    @property
    def timestamp(self) -> Timestamp:
        """Timestamp recorded for the repeat transition."""
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value: Timestamp) -> None:
        """Set repeat timestamp."""
        self._timestamp = value
        self._timestamp.parent = self
        self.mark_dirty()

    @property
    def is_completed(self) -> bool:
        """Whether this repeat transition moved into a done TODO state."""
        return (
            self._document is not None
            and self._after is not None
            and self._after in self._document.done_states
        )

    def attach_document(self, value: Document | None) -> None:
        """Attach owning document reference without changing dirty state."""
        self._document = value

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
        after = f'"{self._after or ""}"'
        before = f'"{self._before or ""}"'
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
    r"""Plain list element containing mutable [org_parser.element.ListItem][] instances.

    Example:
    ```python
    >>> from org_parser.element import ListItem
    >>> from org_parser import loads
    >>> document = loads('''
    ... - Item 0
    ... - Item 1
    ... ''')
    >>> document.body[0][0].checkbox = "X"
    >>> document.body[0][1].bullet = '+'
    >>> print(str(document))
    - [X] Item 0
    + Item 1
    ```
    """

    def __init__(
        self,
        *,
        items: Sequence[ListItem] = (),
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._items = list(items)
        self._adopt_items(self._items)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> List:
        """Create a [org_parser.element.List][] from a ``list`` node."""
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

        def on_items_mutation(wrapped: DirtyList[ListItem]) -> None:
            self._items = list(wrapped)
            self._adopt_items(self._items)
            self.mark_dirty()

        return DirtyList(self._items, on_mutation=on_items_mutation)

    @items.setter
    def items(self, value: list[ListItem]) -> None:
        """Set list items."""
        self.set_items(value)

    def set_items(self, value: list[ListItem], *, mark_dirty: bool = True) -> None:
        """Set list items with optional dirty propagation."""
        self._items = list(value)
        self._adopt_items(self._items)
        if mark_dirty:
            self.mark_dirty()

    def append_item(self, item: ListItem, *, mark_dirty: bool = True) -> None:
        """Append one list item with optional dirty propagation."""
        self._items = [*self._items, item]
        self._adopt_items(self._items)
        if mark_dirty:
            self.mark_dirty()

    def insert_item(self, index: int, item: ListItem) -> None:
        """Insert one list item at *index*."""
        items = [*self._items]
        items.insert(index, item)
        self._items = items
        self._adopt_items(self._items)
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


def _extract_single_list_item_node(document: Document) -> ListItem | None:
    """Return the sole list item semantic node from parsed source."""
    if (
        document.keywords
        or len(document.properties) > 0
        or len(document.logbook) > 0
        or document.children
        or len(document.body) != 1
    ):
        return None

    list_element = document.body[0]
    if not isinstance(list_element, List):
        return None
    if len(list_element.items) != 1:
        return None
    return list_element.items[0]


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

    if tag_node.named_child_count > 0:
        return RichText.from_nodes(tag_node.named_children, document=document)

    raw_tag = document.source_for(tag_node).decode()
    trimmed = raw_tag[:-4].rstrip() if raw_tag.endswith(" :: ") else raw_tag
    return RichText(trimmed)


def _extract_first_line(
    node: tree_sitter.Node,
    document: Document,
) -> RichText | None:
    """Return first-line rich text composed from all ``first_line`` objects."""
    return RichText.from_nodes(node.children_by_field_name("first_line"), document=document)


def _indent_non_empty_lines(value: str, prefix: str) -> str:
    """Prefix each non-empty line in *value* with *prefix*."""
    if prefix == "":
        return value
    lines = value.splitlines(keepends=True)
    return "".join(f"{prefix}{line}" if line.strip() != "" else line for line in lines)


def _parse_repeat_first_line(
    first_line: RichText,
) -> tuple[str | None, str | None, Timestamp, bool] | None:
    """Parse one repeat header from a list item's first-line text.

    Returns:
        A tuple of ``(after, before, timestamp, has_remainder)``
        when the line matches repeat syntax, otherwise ``None``.
    """
    if len(first_line.parts) < 2:
        return None

    prefix_part = first_line.parts[0]
    timestamp_part = first_line.parts[1]

    if not isinstance(prefix_part, PlainText) or not isinstance(timestamp_part, Timestamp):
        return None

    parsed_states = _parse_repeat_states(prefix_part.text)
    if parsed_states is None:
        return None
    after, before = parsed_states

    has_remainder = False
    if len(first_line.parts) > 2 and not isinstance(first_line.parts[-1], LineBreak):
        has_remainder = True

    return (
        after,
        before,
        timestamp_part,
        has_remainder,
    )


def _parse_repeat_states(prefix: str) -> tuple[str | None, str | None] | None:
    """Parse ``State <after> from <before>`` with optional/empty states."""
    if not prefix.startswith("State"):
        return None

    rest = prefix[len("State") :]
    if rest == "" or not rest[0].isspace():
        return None

    from_index = _find_repeat_from_token(rest)
    if from_index is None:
        return None

    after = _parse_repeat_state_segment(rest[:from_index])
    if isinstance(after, _InvalidRepeatState):
        return None

    before = _parse_repeat_state_segment(rest[from_index + len("from") :])
    if isinstance(before, _InvalidRepeatState):
        return None

    return after, before


class _InvalidRepeatState:
    """Sentinel type for invalid repeat-state parse segments."""


_INVALID_REPEAT_STATE = _InvalidRepeatState()


def _parse_repeat_state_segment(segment: str) -> str | None | _InvalidRepeatState:
    """Parse one repeat state segment into ``str | None`` or invalid marker."""
    stripped = segment.strip()
    if stripped in {"", '""'}:
        return None

    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        value = stripped[1:-1]
        if '"' in value:
            return _INVALID_REPEAT_STATE
        return value if value != "" else None

    return _INVALID_REPEAT_STATE


def _find_repeat_from_token(rest: str) -> int | None:
    """Return ``from`` token index outside quotes with whitespace boundaries."""
    in_quote = False
    for index, char in enumerate(rest):
        if char == '"':
            in_quote = not in_quote
            continue
        if in_quote:
            continue
        if not rest.startswith("from", index):
            continue

        previous = rest[index - 1] if index > 0 else ""
        next_index = index + len("from")
        following = rest[next_index] if next_index < len(rest) else ""
        if previous.isspace() and following.isspace():
            return index

    if in_quote:
        return None
    return None


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
    """Build one [org_parser.element.Indent][] for a list-item body ``indent`` node."""
    return Indent.from_node(node, document, parent=parent, child_factory=_extract_list_body_element)
