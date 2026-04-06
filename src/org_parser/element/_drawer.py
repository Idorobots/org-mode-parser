"""Drawer element implementations for Org Mode drawers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping, Sequence
from typing import TYPE_CHECKING, Any

from org_parser._node import is_error_node
from org_parser._nodes import INDENT, NODE_PROPERTY
from org_parser.element._dirty_list import DirtyList
from org_parser.element._dispatch import body_element_factories
from org_parser.element._element import (
    Element,
    build_semantic_repr,
    coerce_element_body,
    element_from_error_or_unknown,
    ensure_trailing_newline,
    node_source,
)
from org_parser.element._list import List, ListItem, Repeat
from org_parser.element._structure import Indent
from org_parser.element._structure_recovery import attach_affiliated_keywords
from org_parser.text._rich_text import RichText
from org_parser.time import Clock

if TYPE_CHECKING:
    from collections.abc import Callable

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["Drawer", "Logbook", "Properties"]

PropertyValue = Any
_DRAWER_START_TEXT = "drawer_start_text"
_TRUNCATED_DRAWER_MESSAGE = "Unterminated drawer (missing :END: marker)"


def _drawer_marker_error_message() -> str:
    """Return the canonical parse-error message for malformed drawer markers."""
    from org_parser.document._document import drawer_marker_trailing_message

    return drawer_marker_trailing_message()


def _report_direct_drawer_parse_errors(node: tree_sitter.Node, document: Document) -> None:
    """Report direct parse-error children on one drawer node.

    Truncated drawers often surface as one direct ``ERROR`` child where the
    terminating ``:END:`` marker is expected.
    """
    for child in node.named_children:
        if is_error_node(child):
            document.report_error(child, _TRUNCATED_DRAWER_MESSAGE)


class Drawer(Element):
    r"""Generic drawer element with a mutable name and body.

    Args:
        name: Drawer name without surrounding colons.
        body: Parsed child elements contained in the drawer.
        parent: Optional parent owner object.

    Example:
    ```python
    >>> from org_parser.element import Drawer
    >>> d = Drawer.from_source('''\
    ... :DRAWER:
    ... some content
    ... :END:
    ... ''')
    >>> d.name
    'DRAWER'
    >>> d.body_text
    'some content\n'
    ```
    """

    def __init__(
        self,
        *,
        name: str,
        body: Sequence[Element] = (),
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._name = name
        self._body = list(body)
        self._adopt_body(self._body)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Drawer:
        """Create a [org_parser.element.Drawer][] from a tree-sitter ``drawer`` node."""
        name_node = node.child_by_field_name("name")
        name = "" if name_node is None else document.source_for(name_node).decode()
        end_text_node = node.child_by_field_name("end_text")
        if end_text_node is not None:
            document.report_error(end_text_node, _drawer_marker_error_message())
        drawer_body = [
            _extract_drawer_body_element(child, document)
            for child in node.children_by_field_name("body")
        ]
        attach_affiliated_keywords(drawer_body)
        drawer = cls(
            name=name,
            body=drawer_body,
            parent=parent,
        )
        drawer._node = node
        drawer._document = document
        _report_direct_drawer_parse_errors(node, document)
        return drawer

    @property
    def name(self) -> str:
        """Drawer name without surrounding colons."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set drawer name."""
        self._name = value
        self.mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Mutable list of drawer body elements."""

        def on_body_mutation(wrapped: DirtyList[Element]) -> None:
            self._body = list(wrapped)
            self._adopt_body(self._body)
            self.mark_dirty()

        return DirtyList(self._body, on_mutation=on_body_mutation)

    @body.setter
    def body(self, value: Sequence[Element] | Element | str) -> None:
        """Set drawer body."""
        self._body = list(coerce_element_body(value))
        self._adopt_body(self._body)
        self.mark_dirty()

    @property
    def body_text(self) -> str:
        """Stringified text of all drawer body elements."""
        return "".join(str(element) for element in self._body)

    def _adopt_body(self, body: Sequence[Element]) -> None:
        """Assign this drawer as parent for all body elements."""
        for element in body:
            element.parent = self

    def reformat(self) -> None:
        """Mark body and this drawer dirty for scratch-built rendering."""
        for element in self._body:
            element.reformat()
        self.mark_dirty()

    def __str__(self) -> str:
        """Render drawer text preserving source text while clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)

        body_text = "".join(ensure_trailing_newline(str(element)) for element in self._body)
        return f":{self._name}:\n{body_text}:END:\n"

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("Drawer", name=self._name, body=self._body)

    def __iter__(self) -> Iterator[Element]:
        """Iterate over body elements."""
        return iter(self._body)

    def __len__(self) -> int:
        """Return number of body elements."""
        return len(self._body)

    def __getitem__(self, index: int | slice) -> Element | list[Element]:
        """Return one body element (or body slice)."""
        return self._body[index]


class Logbook(Drawer):
    """Specialized drawer for ``:LOGBOOK:`` entries.

    Example:
    ```python
    >>> from org_parser.element import Logbook
    >>> d = Logbook.from_source('''\
    ... :LOGBOOK:
    ... CLOCK: [2025-10-10]
    ... - State "DONE"       from "TODO"       <2025-10-10>
    ... :END:
    ... ''')
    >>> d.name
    'LOGBOOK'
    >>> len(d.clock_entries)
    1
    >>> len(d.repeats)
    1
    ```
    """

    def __init__(
        self,
        *,
        body: Sequence[Element] = (),
        clock_entries: Sequence[Clock] = (),
        repeats: Sequence[Repeat] = (),
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(
            name="LOGBOOK",
            body=body,
            parent=parent,
        )
        self._clock_entries = list(clock_entries)
        self._repeats: list[Repeat] = list(repeats)
        self._adopt_body(self._clock_entries)
        self._sync_clock_entries_into_body()
        self._sync_repeats_into_body(mark_dirty=False)

    @property
    def body(self) -> list[Element]:
        """Mutable list of drawer body elements."""

        def on_body_mutation(wrapped: DirtyList[Element]) -> None:
            self._body = list(wrapped)
            self._adopt_body(self._body)
            self._clock_entries = [element for element in self._body if isinstance(element, Clock)]
            self._repeats = _extract_existing_logbook_repeats(self._body)
            self.mark_dirty()

        return DirtyList(self._body, on_mutation=on_body_mutation)

    @body.setter
    def body(self, value: Sequence[Element] | Element | str) -> None:
        """Set drawer body and synchronize extracted logbook entry caches."""
        self._body = list(coerce_element_body(value))
        self._adopt_body(self._body)
        self._clock_entries = [element for element in self._body if isinstance(element, Clock)]
        self._repeats = _extract_existing_logbook_repeats(self._body)
        self.mark_dirty()

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Logbook:
        """Create a [org_parser.element.Logbook][] from ``logbook_drawer`` node."""
        end_text_node = node.child_by_field_name("end_text")
        if end_text_node is not None:
            document.report_error(end_text_node, _drawer_marker_error_message())
        body = [
            _extract_drawer_body_element(child, document)
            for child in node.children_by_field_name("body")
        ]
        attach_affiliated_keywords(body)
        repeats = _extract_logbook_repeats(body, document)
        clock_entries = [element for element in body if isinstance(element, Clock)]
        logbook = cls(
            body=body,
            clock_entries=clock_entries,
            repeats=repeats,
            parent=parent,
        )
        logbook._node = node
        logbook._document = document
        _report_direct_drawer_parse_errors(node, document)
        return logbook

    @property
    def clock_entries(self) -> list[Clock]:
        """Clock entries extracted from logbook body."""

        def on_clock_entries_mutation(wrapped: DirtyList[Clock]) -> None:
            self._clock_entries = list(wrapped)
            self._adopt_body(self._clock_entries)
            self._sync_clock_entries_into_body()
            self.mark_dirty()

        return DirtyList(self._clock_entries, on_mutation=on_clock_entries_mutation)

    @clock_entries.setter
    def clock_entries(self, value: list[Clock]) -> None:
        """Set logbook clock entries."""
        self._clock_entries = list(value)
        self._adopt_body(self._clock_entries)
        self._sync_clock_entries_into_body()
        self.mark_dirty()

    @property
    def repeats(self) -> list[Repeat]:
        """Repeated task entries extracted from list items in this logbook."""

        def on_repeats_mutation(wrapped: DirtyList[Repeat]) -> None:
            self._repeats = list(wrapped)
            self._sync_repeats_into_body(mark_dirty=True)
            self.mark_dirty()

        return DirtyList(self._repeats, on_mutation=on_repeats_mutation)

    @repeats.setter
    def repeats(self, value: list[Repeat]) -> None:
        """Set logbook repeat entries."""
        self._repeats = list(value)
        self._sync_repeats_into_body(mark_dirty=True)
        self.mark_dirty()

    def reformat(self) -> None:
        """Mark all logbook children and this drawer dirty."""
        for element in self._body:
            element.reformat()
        for clock in self._clock_entries:
            clock.reformat()
        for repeat in self._repeats:
            repeat.reformat()
        self.mark_dirty()

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr(
            "Logbook",
            body=self._body,
            clock_entries=self._clock_entries,
            repeats=self._repeats,
        )

    def _sync_clock_entries_into_body(self) -> None:
        """Synchronize explicit clock entries into concrete logbook body order."""
        first_clock_index = next(
            (index for index, element in enumerate(self._body) if isinstance(element, Clock)),
            None,
        )
        body_without_clocks = [element for element in self._body if not isinstance(element, Clock)]

        if not self._clock_entries:
            self._body = body_without_clocks
            self._adopt_body(self._body)
            return

        insert_at = len(body_without_clocks)
        if first_clock_index is not None:
            insert_at = len(
                [
                    element
                    for element in self._body[:first_clock_index]
                    if not isinstance(element, Clock)
                ]
            )

        updated_body = [
            *body_without_clocks[:insert_at],
            *self._clock_entries,
            *body_without_clocks[insert_at:],
        ]
        self._body = updated_body
        self._adopt_body(self._body)

    def _sync_repeats_into_body(self, *, mark_dirty: bool) -> None:
        """Synchronize explicit repeat entries into a concrete logbook list."""
        if self._document is not None:
            for repeat in self._repeats:
                repeat.attach_document(self._document)

        target_list: List | None = None
        for element in _iter_repeat_candidate_lists(self.body):
            if any(isinstance(item, Repeat) for item in element.items):
                target_list = element
                break

        if target_list is None:
            if not self._repeats:
                return
            target_list = List(items=list(self._repeats), parent=self)
            if mark_dirty:
                self.body = [*self.body, target_list]
            else:
                self.append_to_body_without_dirty(target_list)
            return

        target_list.set_items(list(self._repeats), mark_dirty=mark_dirty)

    def append_to_body_without_dirty(self, element: Element) -> None:
        """Append one body element without changing this drawer's dirty state."""
        self._body = [*self._body, element]
        self._adopt_body(self._body)


class Properties(Element, MutableMapping[str, PropertyValue]):
    """Property drawer element with dictionary-like mutable access.

    Example:
    ```python
    >>> from org_parser.element import Properties
    >>> d = Properties.from_source('''\
    ... :PROPERTIES:
    ... :key: Value
    ... :END:
    ... ''')
    >>> d.name
    'PROPERTIES'
    >>> d["key"]
    'Value
    ```
    """

    def __init__(
        self,
        *,
        properties: Mapping[str, PropertyValue] | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._properties: dict[str, PropertyValue] = {}
        if properties is not None:
            for key, value in properties.items():
                self._set_property(key, value, mark_dirty=False)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Properties:
        """Create a [org_parser.element.Properties][] from ``property_drawer`` node."""
        properties = cls(parent=parent)
        end_text_node = node.child_by_field_name("end_text")
        if end_text_node is not None:
            document.report_error(end_text_node, _drawer_marker_error_message())
        for child in node.named_children:
            if child.type != NODE_PROPERTY:
                continue
            name_node = child.child_by_field_name("name")
            if name_node is None:
                continue
            key = document.source_for(name_node).decode()
            value_node = child.child_by_field_name("value")
            value = (
                RichText.from_node(value_node, document=document, parent=properties)
                if value_node is not None
                else RichText("")
            )
            properties._set_property(key, value, mark_dirty=False)
        properties._node = node
        properties._document = document
        _report_direct_drawer_parse_errors(node, document)
        return properties

    def _set_property(
        self,
        key: str,
        value: PropertyValue,
        *,
        mark_dirty: bool,
    ) -> None:
        """Set one property value with optional dirty propagation."""
        if key in self._properties:
            del self._properties[key]
        self._properties[key] = value
        if isinstance(value, RichText):
            value.parent = self
        if mark_dirty:
            self.mark_dirty()

    def __getitem__(self, key: str) -> PropertyValue:
        """Return the stored value for one property key."""
        return self._properties[key]

    def __setitem__(self, key: str, value: PropertyValue) -> None:
        """Set one property value."""
        self._set_property(key, value, mark_dirty=True)

    def __delitem__(self, key: str) -> None:
        """Delete one property key."""
        del self._properties[key]
        self.mark_dirty()

    def __iter__(self) -> Iterator[str]:
        """Iterate over property keys in insertion order."""
        return iter(self._properties)

    def __len__(self) -> int:
        """Return number of stored properties."""
        return len(self._properties)

    def reformat(self) -> None:
        """Mark rich-text values and this drawer dirty."""
        for value in self._properties.values():
            if isinstance(value, RichText):
                value.reformat()
        self.mark_dirty()

    def __str__(self) -> str:
        """Render property drawer preserving source text while clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)

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


def _extract_drawer_body_element(
    node: tree_sitter.Node,
    document: Document,
    *,
    parent: Document | Heading | Element | None = None,
) -> Element:
    """Build one semantic element object for a drawer body child node."""
    if node.type == _DRAWER_START_TEXT:
        return element_from_error_or_unknown(
            node,
            document,
            parent=parent,
            error_message=_drawer_marker_error_message(),
        )
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
    """Build one [org_parser.element.Indent][] for a drawer body ``indent`` node."""
    return Indent.from_node(
        node, document, parent=parent, child_factory=_extract_drawer_body_element
    )


def _extract_logbook_repeats(body: list[Element], document: Document) -> list[Repeat]:
    """Convert repeat-form list items in logbook lists into [org_parser.element.Repeat][].

    Each list item body is parsed directly from tree-sitter fields, so the
    repeat parser receives the full continuation payload as-is.
    """
    repeats: list[Repeat] = []
    for element in _iter_repeat_candidate_lists(body):
        updated_items: list[ListItem] = []
        converted = False
        for item in element.items:
            if isinstance(item, Repeat):
                updated_items.append(item)
                repeats.append(item)
                continue
            repeat = Repeat.from_list_item(item, document)
            if repeat is None:
                updated_items.append(item)
                continue
            updated_items.append(repeat)
            repeats.append(repeat)
            converted = True
        if converted:
            element.set_items(updated_items, mark_dirty=False)
    return repeats


def _extract_existing_logbook_repeats(body: list[Element]) -> list[Repeat]:
    """Collect repeat entries already present in logbook body list items."""
    repeats: list[Repeat] = []
    for element in _iter_repeat_candidate_lists(body):
        repeats.extend(item for item in element.items if isinstance(item, Repeat))
    return repeats


def _iter_repeat_candidate_lists(elements: list[Element]) -> Iterator[List]:
    """Yield lists scanned for repeat conversion in one logbook body stream."""
    for element in elements:
        if isinstance(element, List):
            yield element
            continue
        if isinstance(element, Indent):
            yield from _iter_repeat_candidate_lists(element.body)
