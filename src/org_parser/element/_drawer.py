"""Drawer element implementations for Org Mode drawers."""

from __future__ import annotations

from collections.abc import Iterator, MutableMapping, Sequence
from typing import TYPE_CHECKING

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
from org_parser.element._element import Element, build_semantic_repr
from org_parser.element._indent_block import IndentBlock
from org_parser.element._list import List, ListItem, Repeat
from org_parser.element._list_recovery import recover_lists
from org_parser.text._rich_text import RichText
from org_parser.time import Clock

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["Drawer", "Logbook", "Properties"]

_PARAGRAPH = "paragraph"
_ORG_TABLE = "org_table"
_TABLEEL_TABLE = "tableel_table"
_CLOCK = "clock"
_DRAWER = "drawer"
_LOGBOOK_DRAWER = "logbook_drawer"
_PROPERTY_DRAWER = "property_drawer"
_NODE_PROPERTY = "node_property"
_CENTER_BLOCK = "center_block"
_QUOTE_BLOCK = "quote_block"
_SPECIAL_BLOCK = "special_block"
_DYNAMIC_BLOCK = "dynamic_block"
_COMMENT_BLOCK = "comment_block"
_EXAMPLE_BLOCK = "example_block"
_EXPORT_BLOCK = "export_block"
_SRC_BLOCK = "src_block"
_VERSE_BLOCK = "verse_block"
_FIXED_WIDTH = "fixed_width"
_LIST_ITEM = "list_item"
_BLOCK = "block"


class Drawer(Element):
    """Generic drawer element with a mutable name and body.

    Args:
        name: Drawer name without surrounding colons.
        body: Parsed child elements contained in the drawer.
        parent: Optional parent owner object.
        source_text: Optional verbatim source text.
    """

    def __init__(
        self,
        *,
        name: str,
        body: list[Element] | None = None,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(node_type=_DRAWER, source_text=source_text, parent=parent)
        self._name = name
        self._body = body if body is not None else []
        self._adopt_body(self._body)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        source: bytes,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Drawer:
        """Create a :class:`Drawer` from a tree-sitter ``drawer`` node."""
        name_node = node.child_by_field_name("name")
        name = (
            source[name_node.start_byte : name_node.end_byte].decode()
            if name_node is not None
            else ""
        )
        drawer = cls(
            name=name,
            body=_coalesce_list_items(
                [
                    _extract_drawer_body_element(child, source)
                    for child in node.children_by_field_name("body")
                ],
                parent=parent,
            ),
            parent=parent,
            source_text=source[node.start_byte : node.end_byte].decode(),
        )
        drawer._node = node
        return drawer

    @property
    def name(self) -> str:
        """Drawer name without surrounding colons."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set drawer name and mark the drawer as dirty."""
        self._name = value
        self._mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Mutable list of drawer body elements."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set drawer body and mark the drawer as dirty."""
        self._body = value
        self._adopt_body(self._body)
        self._mark_dirty()

    def _adopt_body(self, body: Sequence[Element]) -> None:
        """Assign this drawer as parent for all body elements."""
        for element in body:
            element.set_parent(self, mark_dirty=False)

    def __str__(self) -> str:
        """Render drawer text preserving source text while clean."""
        if not self.dirty and self._node is not None:
            return self.source_text

        body_text = "".join(
            _ensure_trailing_newline(str(element)) for element in self._body
        )
        return f":{self._name}:\n{body_text}:END:\n"

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("Drawer", name=self._name, body=self._body)


class Logbook(Drawer):
    """Specialized drawer for ``:LOGBOOK:`` entries."""

    def __init__(
        self,
        *,
        body: list[Element] | None = None,
        clock_entries: list[Clock] | None = None,
        repeats: list[Repeat] | None = None,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(
            name="LOGBOOK",
            body=body,
            parent=parent,
            source_text=source_text,
        )
        self._node_type = _LOGBOOK_DRAWER
        self._clock_entries = clock_entries if clock_entries is not None else []
        self._repeats: list[Repeat] = repeats if repeats is not None else []
        self._adopt_body(self._clock_entries)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        source: bytes,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Logbook:
        """Create a :class:`Logbook` from ``logbook_drawer`` node."""
        body = _coalesce_list_items(
            [
                _extract_drawer_body_element(child, source)
                for child in node.children_by_field_name("body")
            ],
            parent=parent,
        )
        repeats = _extract_logbook_repeats(body)
        clock_entries = [element for element in body if isinstance(element, Clock)]
        logbook = cls(
            body=body,
            clock_entries=clock_entries,
            repeats=repeats,
            parent=parent,
            source_text=source[node.start_byte : node.end_byte].decode(),
        )
        logbook._node = node
        return logbook

    @classmethod
    def from_drawer(cls, drawer: Drawer) -> Logbook:
        """Create a :class:`Logbook` from a generic drawer instance."""
        body = list(drawer.body)
        repeats = _extract_logbook_repeats(body)
        clock_entries = [element for element in body if isinstance(element, Clock)]
        return cls(body=body, clock_entries=clock_entries, repeats=repeats)

    @property
    def clock_entries(self) -> list[Clock]:
        """Clock entries extracted from logbook body."""
        return self._clock_entries

    @clock_entries.setter
    def clock_entries(self, value: list[Clock]) -> None:
        """Set logbook clock entries and mark the drawer as dirty."""
        self._clock_entries = value
        self._adopt_body(self._clock_entries)
        self._mark_dirty()

    @property
    def repeats(self) -> list[Repeat]:
        """Repeated task entries extracted from list items in this logbook."""
        return self._repeats

    @repeats.setter
    def repeats(self, value: list[Repeat]) -> None:
        """Set logbook repeat entries and mark the drawer as dirty."""
        self._repeats = value
        _sync_logbook_repeat_list(self, self._repeats)
        self._mark_dirty()

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr(
            "Logbook",
            body=self._body,
            clock_entries=self._clock_entries,
            repeats=self._repeats,
        )


class Properties(Element, MutableMapping[str, RichText]):
    """Property drawer element with dictionary-like mutable access."""

    def __init__(
        self,
        *,
        properties: dict[str, RichText] | None = None,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(
            node_type=_PROPERTY_DRAWER,
            source_text=source_text,
            parent=parent,
        )
        self._properties: dict[str, RichText] = {}
        if properties is not None:
            for key, value in properties.items():
                self._set_property(key, value, mark_dirty=False)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        source: bytes,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Properties:
        """Create a :class:`Properties` from ``property_drawer`` node."""
        properties = cls(
            parent=parent,
            source_text=source[node.start_byte : node.end_byte].decode(),
        )
        for child in node.named_children:
            if child.type != _NODE_PROPERTY:
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            key = source[name_node.start_byte : name_node.end_byte].decode()
            value_node = child.child_by_field_name("value")
            value = (
                RichText.from_node(value_node, source)
                if value_node is not None
                else RichText("")
            )
            properties._set_property(key, value, mark_dirty=False)
        properties._node = node
        return properties

    @classmethod
    def from_drawer(cls, drawer: Drawer) -> Properties:
        """Create a :class:`Properties` value from a generic drawer body."""
        properties = cls()
        for element in drawer.body:
            line = element.source_text.rstrip("\n")
            if not line.startswith(":"):
                continue
            rest = line[1:]
            delimiter_index = rest.find(":")
            if delimiter_index <= 0:
                continue
            key = rest[:delimiter_index]
            value_text = rest[delimiter_index + 1 :].strip()
            properties._set_property(key, RichText(value_text), mark_dirty=False)
        return properties

    def _set_property(
        self,
        key: str,
        value: RichText,
        *,
        mark_dirty: bool,
    ) -> None:
        """Set one property value with optional dirty propagation."""
        if key in self._properties:
            del self._properties[key]
        self._properties[key] = value
        value.set_parent(self, mark_dirty=False)
        if mark_dirty:
            self._mark_dirty()

    def __getitem__(self, key: str) -> RichText:
        """Return the rich-text value for one property key."""
        return self._properties[key]

    def __setitem__(self, key: str, value: RichText) -> None:
        """Set one property value and mark drawer as dirty."""
        self._set_property(key, value, mark_dirty=True)

    def __delitem__(self, key: str) -> None:
        """Delete one property key and mark drawer as dirty."""
        del self._properties[key]
        self._mark_dirty()

    def __iter__(self) -> Iterator[str]:
        """Iterate over property keys in insertion order."""
        return iter(self._properties)

    def __len__(self) -> int:
        """Return number of stored properties."""
        return len(self._properties)

    def __str__(self) -> str:
        """Render property drawer preserving source text while clean."""
        if not self.dirty and self._node is not None:
            return self.source_text

        lines = [":PROPERTIES:\n"]
        for key, value in self._properties.items():
            rendered_value = str(value)
            if rendered_value == "":
                lines.append(f":{key}:\n")
            else:
                lines.append(f":{key}: {rendered_value}\n")
        lines.append(":END:\n")
        return "".join(lines)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("Properties", properties=self._properties)


def _extract_drawer_body_element(node: tree_sitter.Node, source: bytes) -> Element:
    """Build one semantic element object for a drawer body child node."""
    from org_parser.element._paragraph import Paragraph
    from org_parser.element._table import Table

    if node.type == _BLOCK:
        return _extract_indent_block(node, source)

    dispatch = {
        _PARAGRAPH: Paragraph.from_node,
        _ORG_TABLE: Table.from_node,
        _TABLEEL_TABLE: Table.from_node,
        _CLOCK: Clock.from_node,
        _DRAWER: Drawer.from_node,
        _LOGBOOK_DRAWER: Logbook.from_node,
        _PROPERTY_DRAWER: Properties.from_node,
        _CENTER_BLOCK: CenterBlock.from_node,
        _QUOTE_BLOCK: QuoteBlock.from_node,
        _SPECIAL_BLOCK: SpecialBlock.from_node,
        _DYNAMIC_BLOCK: DynamicBlock.from_node,
        _COMMENT_BLOCK: CommentBlock.from_node,
        _EXAMPLE_BLOCK: ExampleBlock.from_node,
        _EXPORT_BLOCK: ExportBlock.from_node,
        _SRC_BLOCK: SourceBlock.from_node,
        _VERSE_BLOCK: VerseBlock.from_node,
        _FIXED_WIDTH: FixedWidthBlock.from_node,
        _LIST_ITEM: ListItem.from_node,
    }
    factory = dispatch.get(node.type)
    if factory is None:
        return Element.from_node(node, source)
    return factory(node, source)


def _extract_indent_block(node: tree_sitter.Node, source: bytes) -> IndentBlock:
    """Build one :class:`IndentBlock` for a drawer body ``block`` node."""
    return IndentBlock(
        body=[
            _extract_drawer_body_element(child, source)
            for child in node.children_by_field_name("body")
            if child.is_named
        ],
        source_text=source[node.start_byte : node.end_byte].decode(),
    )


def _coalesce_list_items(
    elements: list[Element],
    *,
    parent: Document | Heading | Element | None,
) -> list[Element]:
    """Recover semantic lists from flat drawer body elements."""
    return recover_lists(elements, parent=parent)


def _ensure_trailing_newline(value: str) -> str:
    """Return *value* with one trailing newline when non-empty."""
    if value == "" or value.endswith("\n"):
        return value
    return f"{value}\n"


def _extract_logbook_repeats(body: list[Element]) -> list[Repeat]:
    """Convert repeat-form list items in logbook lists into :class:`Repeat`."""
    repeats: list[Repeat] = []
    for element in body:
        if not isinstance(element, List):
            continue
        updated_items: list[ListItem] = []
        converted = False
        for item in element.items:
            if isinstance(item, Repeat):
                updated_items.append(item)
                repeats.append(item)
                continue
            repeat = Repeat.from_list_item(item)
            if repeat is None:
                updated_items.append(item)
                continue
            updated_items.append(repeat)
            repeats.append(repeat)
            converted = True
        if converted:
            element.set_items(updated_items, mark_dirty=False)
    return repeats


def _sync_logbook_repeat_list(logbook: Logbook, repeats: list[Repeat]) -> None:
    """Synchronize explicit repeat entries into a concrete logbook list."""
    target_list: List | None = None
    for element in logbook.body:
        if not isinstance(element, List):
            continue
        if any(isinstance(item, Repeat) for item in element.items):
            target_list = element
            break

    if target_list is None:
        if not repeats:
            return
        target_list = List(items=list(repeats), parent=logbook)
        logbook.body = [*logbook.body, target_list]
        return

    target_list.items = list(repeats)
