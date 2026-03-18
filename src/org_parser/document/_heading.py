"""Implementation of :class:`Heading` — an Org Mode heading / sub-heading."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.document._body import (
    extract_body_element,
    merge_logbook_drawers,
    merge_properties_drawers,
)
from org_parser.element import (
    Drawer,
    Logbook,
    Properties,
    Repeat,
)
from org_parser.element._element import (
    Element,
    element_from_error_or_unknown,
    reformat_value,
)
from org_parser.element._list_recovery import recover_lists
from org_parser.text._inline import CompletionCounter
from org_parser.text._rich_text import RichText
from org_parser.time import Timestamp

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document

__all__ = ["Heading"]

# Node type names produced by the tree-sitter grammar.
_HEADING = "heading"
_COMPLETION_COUNTER = "completion_counter"
_TAG = "tag"
_PLANNING = "planning"
_PLANNING_KEYWORD = "planning_keyword"
_TIMESTAMP = "timestamp"
_DRAWER = "drawer"
_LOGBOOK_DRAWER = "logbook_drawer"
_PROPERTY_DRAWER = "property_drawer"


class Heading:
    """An Org Mode heading (or sub-heading).

    A heading exposes the parsed components of an Org headline — stars, TODO
    state, priority cookie, title text, tags, completion counter — as well as
    the body elements and any nested sub-headings.

    Args:
        level: The heading level (count of leading ``*`` characters).
        document: The root :class:`Document` that contains this heading.
        parent: The parent :class:`Heading` or :class:`Document`.
        todo: The TODO keyword (e.g. ``"TODO"``, ``"DONE"``), or *None*.
        priority: The priority letter or number (e.g. ``"A"``, ``"1"``), or
            *None*.
        title: The heading title as :class:`RichText`, or *None*.
        counter: Completion counter object (e.g. ``[1/3]``), or *None*.
        tags: A list of tag strings in source order.
        repeated_tasks: Repeated task entries extracted from ``LOGBOOK``.
        body: Body elements of the heading (excludes sub-headings).
        children: Direct sub-headings of this heading.
    """

    def __init__(
        self,
        *,
        level: int,
        document: Document,
        parent: Heading | Document,
        todo: str | None = None,
        priority: str | None = None,
        title: RichText | None = None,
        counter: CompletionCounter | None = None,
        tags: list[str] | None = None,
        scheduled: Timestamp | None = None,
        closed: Timestamp | None = None,
        deadline: Timestamp | None = None,
        properties: Properties | None = None,
        logbook: Logbook | None = None,
        repeated_tasks: list[Repeat] | None = None,
        body: list[Element] | None = None,
        children: list[Heading] | None = None,
    ) -> None:
        self._level = level
        self._document = document
        self._parent = parent
        self._todo = todo
        self._priority = priority
        self._title = title
        self._counter = counter
        self._tags: list[str] = tags if tags is not None else []
        self._scheduled = scheduled
        self._closed = closed
        self._deadline = deadline
        self._properties = properties
        self._logbook = logbook
        self._repeated_tasks: list[Repeat] = (
            repeated_tasks
            if repeated_tasks is not None
            else ([] if logbook is None else logbook.repeats)
        )
        self._body: list[Element] = body if body is not None else []
        self._children: list[Heading] = children if children is not None else []
        self._node: tree_sitter.Node | None = None
        self._dirty = False

        if self._title is not None:
            self._title.parent = self

        self._adopt_properties(self._properties)
        self._adopt_logbook(self._logbook)
        self._sync_repeated_tasks_from_logbook()
        self._adopt_body_elements(self._body)
        self._adopt_children(self._children)

    # -- factory method ------------------------------------------------------

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        *,
        document: Document,
        parent: Heading | Document,
    ) -> Heading:
        """Build a :class:`Heading` (and its sub-tree) from a tree-sitter node.

        Args:
            node: A tree-sitter node of type ``heading``.
            document: The root document that contains this heading.
            parent: The parent :class:`Heading` or :class:`Document`.

        Returns:
            A fully populated :class:`Heading` with recursively built
            children.
        """
        source = document.source
        level = _extract_level(node)
        todo = _extract_todo(node)
        priority = _extract_priority(node)
        title_nodes = node.children_by_field_name("title")
        title = RichText.from_nodes(title_nodes, source, document=document)
        counter = _extract_counter(title_nodes)
        tags = _extract_tags(node)
        scheduled, deadline, closed = _extract_planning(node, source)
        properties, logbook, body = _extract_body(
            node, parent=parent, document=document
        )

        heading = cls(
            level=level,
            document=document,
            parent=parent,
            todo=todo,
            priority=priority,
            title=title,
            counter=counter,
            tags=tags,
            scheduled=scheduled,
            deadline=deadline,
            closed=closed,
            properties=properties,
            logbook=logbook,
            body=body,
        )
        heading._node = node

        # Re-home body elements to this heading instance (not its parent).
        heading._adopt_properties(heading._properties)
        heading._adopt_logbook(heading._logbook)
        heading._adopt_body_elements(heading._body)

        # Recursively build sub-headings.
        for child in node.children:
            if child.type == _HEADING:
                sub = cls.from_node(
                    child,
                    document=document,
                    parent=heading,
                )
                heading._children.append(sub)
            elif child.type == "ERROR" or child.is_missing:
                elem = element_from_error_or_unknown(child, document, parent=heading)
                heading._body.append(elem)

        return heading

    # -- public read-only properties -----------------------------------------

    @property
    def document(self) -> Document:
        """The :class:`Document` that ultimately contains this heading."""
        return self._document

    @document.setter
    def document(self, value: Document) -> None:
        """Set the owning document and mark this heading as dirty."""
        self._document = value
        self._dirty = True
        self._parent.mark_dirty()
        value.mark_dirty()

    @property
    def level(self) -> int:
        """The heading level (count of leading ``*`` characters)."""
        return self._level

    @level.setter
    def level(self, value: int) -> None:
        """Set the heading level and mark this heading as dirty."""
        self._level = value
        self._mark_dirty()

    @property
    def todo(self) -> str | None:
        """The TODO keyword, or *None* if absent."""
        return self._todo

    @todo.setter
    def todo(self, value: str | None) -> None:
        """Set the TODO keyword and mark this heading as dirty."""
        self._todo = value
        self._mark_dirty()

    @property
    def priority(self) -> str | None:
        """The priority value (e.g. ``"A"``, ``"1"``), or *None*."""
        return self._priority

    @priority.setter
    def priority(self, value: str | None) -> None:
        """Set the priority value and mark this heading as dirty."""
        self._priority = value
        self._mark_dirty()

    @property
    def title(self) -> RichText | None:
        """The heading title as :class:`RichText`, or *None*."""
        return self._title

    @title.setter
    def title(self, value: RichText | None) -> None:
        """Set the heading title and mark this heading as dirty."""
        self._title = value
        if self._title is not None:
            self._title.parent = self
        self._mark_dirty()

    @property
    def counter(self) -> CompletionCounter | None:
        """The completion counter object, or *None* if absent."""
        return self._counter

    @counter.setter
    def counter(self, value: CompletionCounter | None) -> None:
        """Set the completion counter and mark this heading as dirty."""
        self._counter = value
        self._mark_dirty()

    @property
    def tags(self) -> list[str]:
        """Tag strings in source order."""
        return self._tags

    @tags.setter
    def tags(self, value: list[str]) -> None:
        """Set tag strings and mark this heading as dirty."""
        self._tags = value
        self._mark_dirty()

    @property
    def scheduled(self) -> Timestamp | None:
        """The ``SCHEDULED`` planning timestamp, or *None*."""
        return self._scheduled

    @scheduled.setter
    def scheduled(self, value: Timestamp | None) -> None:
        """Set the ``SCHEDULED`` planning timestamp and mark dirty."""
        self._scheduled = value
        self._mark_dirty()

    @property
    def closed(self) -> Timestamp | None:
        """The ``CLOSED`` planning timestamp, or *None*."""
        return self._closed

    @closed.setter
    def closed(self, value: Timestamp | None) -> None:
        """Set the ``CLOSED`` planning timestamp and mark dirty."""
        self._closed = value
        self._mark_dirty()

    @property
    def deadline(self) -> Timestamp | None:
        """The ``DEADLINE`` planning timestamp, or *None*."""
        return self._deadline

    @deadline.setter
    def deadline(self, value: Timestamp | None) -> None:
        """Set the ``DEADLINE`` planning timestamp and mark dirty."""
        self._deadline = value
        self._mark_dirty()

    @property
    def body(self) -> list[Element]:
        """Body elements (excludes sub-headings)."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set body elements and mark this heading as dirty."""
        self._body = value
        self._adopt_body_elements(self._body)
        self._mark_dirty()

    @property
    def properties(self) -> Properties | None:
        """Merged heading ``PROPERTIES`` drawer, or *None*."""
        return self._properties

    @properties.setter
    def properties(self, value: Properties | None) -> None:
        """Set merged heading ``PROPERTIES`` drawer and mark dirty."""
        self._properties = value
        self._adopt_properties(self._properties)
        self._mark_dirty()

    @property
    def logbook(self) -> Logbook | None:
        """Merged heading ``LOGBOOK`` drawer, or *None*."""
        return self._logbook

    @logbook.setter
    def logbook(self, value: Logbook | None) -> None:
        """Set merged heading ``LOGBOOK`` drawer and mark dirty."""
        self._logbook = value
        self._adopt_logbook(self._logbook)
        self._sync_repeated_tasks_from_logbook()
        self._mark_dirty()

    @property
    def repeated_tasks(self) -> list[Repeat]:
        """Repeated task entries extracted from this heading's logbook."""
        if self._logbook is None:
            self._ensure_logbook_for_repeats()
            self._sync_repeated_tasks_from_logbook()
        return self._repeated_tasks

    @repeated_tasks.setter
    def repeated_tasks(self, value: list[Repeat]) -> None:
        """Set repeated tasks and synchronize them into the logbook drawer."""
        self._repeated_tasks = value
        logbook = self._ensure_logbook_for_repeats()
        logbook.repeats = self._repeated_tasks
        self._mark_dirty()

    def add_repeated_task(self, repeat: Repeat) -> None:
        """Append one repeated task and synchronize it into the logbook."""
        self._repeated_tasks = [*self._repeated_tasks, repeat]
        logbook = self._ensure_logbook_for_repeats()
        logbook.repeats = self._repeated_tasks
        self._mark_dirty()

    @property
    def parent(self) -> Heading | Document:
        """The parent :class:`Heading` or :class:`Document`."""
        return self._parent

    @parent.setter
    def parent(self, value: Heading | Document) -> None:
        """Set the parent reference without changing dirty state."""
        self._parent = value

    @property
    def children(self) -> list[Heading]:
        """Direct sub-headings."""
        return self._children

    @children.setter
    def children(self, value: list[Heading]) -> None:
        """Set direct sub-headings and mark this heading as dirty."""
        self._children = value
        self._adopt_children(self._children)
        self._mark_dirty()

    @property
    def dirty(self) -> bool:
        """Whether this heading has been mutated after creation."""
        return self._dirty

    def _mark_dirty(self) -> None:
        """Mark this heading dirty and bubble to its parent chain."""
        if self._dirty:
            return
        self._dirty = True
        self._parent.mark_dirty()

    def mark_dirty(self) -> None:
        """Mark this heading dirty and bubble to its parent chain."""
        self._mark_dirty()

    def reformat(self) -> None:
        """Recursively mark heading descendants dirty, then self dirty."""
        reformat_value(self._title)
        reformat_value(self._counter)
        reformat_value(self._scheduled)
        reformat_value(self._deadline)
        reformat_value(self._closed)
        reformat_value(self._properties)
        reformat_value(self._logbook)
        reformat_value(self._repeated_tasks)
        reformat_value(self._body)
        reformat_value(self._children)
        self.mark_dirty()

    def _adopt_body_elements(self, body: list[Element]) -> None:
        """Assign this heading as parent for all body elements."""
        for element in body:
            element.parent = self

    def _adopt_properties(self, value: Properties | None) -> None:
        """Assign this heading as parent for merged properties drawer."""
        if value is None:
            return
        value.parent = self

    def _adopt_logbook(self, value: Logbook | None) -> None:
        """Assign this heading as parent for merged logbook drawer."""
        if value is None:
            return
        value.parent = self

    def _sync_repeated_tasks_from_logbook(self) -> None:
        """Synchronize local repeated-task cache from the current logbook."""
        if self._logbook is None:
            self._repeated_tasks = []
            return
        self._repeated_tasks = self._logbook.repeats

    def _ensure_logbook_for_repeats(self) -> Logbook:
        """Return heading logbook, creating one when absent."""
        if self._logbook is None:
            self._logbook = Logbook(parent=self)
            self._adopt_logbook(self._logbook)
        return self._logbook

    def _adopt_children(self, children: list[Heading]) -> None:
        """Assign this heading as parent for direct sub-headings."""
        for child in children:
            child.parent = self

    @property
    def siblings(self) -> list[Heading]:
        """Other headings at the same level under the same parent."""
        return [h for h in self._parent.children if h is not self]

    # -- dunder protocols ----------------------------------------------------

    def __str__(self) -> str:
        """Return a textual representation of this heading and its body.

        When the heading is clean and still backed by a parse tree, this
        returns the exact source slice that spans the heading line and body
        section only, excluding any sub-headings. Once dirty, this is rebuilt
        from semantic fields.
        """
        if not self._dirty and self._node is not None:
            end_byte = self._node.end_byte
            first_subheading = _find_first_subheading(self._node)
            if first_subheading is not None:
                end_byte = first_subheading.start_byte
            return self.document.source[self._node.start_byte : end_byte].decode()

        return _render_heading_dirty(self)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        parts = [f"level={self._level!r}"]
        optional_parts = [
            ("todo", self._todo),
            ("priority", self._priority),
            ("title", self._title),
            ("counter", self._counter),
            ("scheduled", self._scheduled),
            ("deadline", self._deadline),
            ("closed", self._closed),
            ("properties", self._properties),
            ("logbook", self._logbook),
        ]
        parts.extend(
            f"{name}={value!r}" for name, value in optional_parts if value is not None
        )

        list_parts = [
            ("tags", self._tags),
            ("repeated_tasks", self._repeated_tasks),
            ("body", self._body),
            ("children", self._children),
        ]
        parts.extend(f"{name}={value!r}" for name, value in list_parts if value)
        return f"Heading({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Private helpers — field extraction from tree-sitter nodes
# ---------------------------------------------------------------------------


def _extract_level(node: tree_sitter.Node) -> int:
    """Return the heading level from the ``stars`` field."""
    stars_node = node.child_by_field_name("stars")
    if stars_node is None or stars_node.text is None:
        return 0  # pragma: no cover - defensive
    return len(stars_node.text)


def _extract_todo(node: tree_sitter.Node) -> str | None:
    """Return the TODO keyword text, or *None*."""
    todo_node = node.child_by_field_name("todo")
    if todo_node is None or todo_node.text is None:
        return None
    # The todo_keyword node includes trailing whitespace; strip it.
    return todo_node.text.decode().strip() or None


def _extract_priority(node: tree_sitter.Node) -> str | None:
    """Return the priority value (letter or number), or *None*.

    The priority node stores its value in the ``value`` field.
    """
    prio_node = node.child_by_field_name("priority")
    if prio_node is None or prio_node.text is None:
        return None
    value_node = prio_node.child_by_field_name("value")
    if value_node is None or value_node.text is None:
        return None
    return value_node.text.decode() or None


def _extract_counter(
    title_nodes: list[tree_sitter.Node],
) -> CompletionCounter | None:
    """Scan title children for a ``completion_counter`` and return its inner value.

    The completion counter node stores its value in the ``value`` field.
    """
    for n in title_nodes:
        if n.type == _COMPLETION_COUNTER:
            value_node = n.child_by_field_name("value")
            if value_node is None or value_node.text is None:
                continue  # pragma: no cover - defensive
            value = value_node.text.decode()
            if value == "":
                return None
            return CompletionCounter(value)
    return None


def _extract_tags(node: tree_sitter.Node) -> list[str]:
    """Return the list of tag strings from the ``tags`` field."""
    tags_node = node.child_by_field_name("tags")
    if tags_node is None:
        return []
    return [
        child.text.decode()
        for child in tags_node.named_children
        if child.type == _TAG and child.text is not None
    ]


def _extract_body(
    node: tree_sitter.Node,
    *,
    parent: Heading | Document,
    document: Document | None = None,
) -> tuple[Properties | None, Logbook | None, list[Element]]:
    """Return merged drawers and body elements for heading section content."""
    properties_drawers: list[Properties] = []
    logbook_drawers: list[Logbook] = []
    body: list[Element] = []
    properties_node = node.child_by_field_name("properties")
    if properties_node is not None:
        properties_drawers.append(
            Properties.from_node(properties_node, document, parent=parent)
        )

    section_node = node.child_by_field_name("body")
    if section_node is None:
        return (
            merge_properties_drawers(properties_drawers, parent=parent),
            merge_logbook_drawers(logbook_drawers, parent=parent),
            body,
        )

    for child in section_node.named_children:
        if child.type == _PROPERTY_DRAWER:
            properties_drawers.append(
                Properties.from_node(child, document, parent=parent)
            )
        elif child.type == _LOGBOOK_DRAWER:
            logbook_drawers.append(Logbook.from_node(child, document, parent=parent))
        elif child.type == _DRAWER:
            drawer = Drawer.from_node(child, document, parent=parent)
            drawer_name = drawer.name.upper()
            if drawer_name == "PROPERTIES":
                properties_drawers.append(Properties.from_drawer(drawer))
            elif drawer_name == "LOGBOOK":
                logbook_drawers.append(Logbook.from_drawer(drawer))
            else:
                body.append(drawer)
        else:
            body.append(extract_body_element(child, parent=parent, document=document))

    return (
        merge_properties_drawers(properties_drawers, parent=parent),
        merge_logbook_drawers(logbook_drawers, parent=parent),
        recover_lists(body, parent=parent),
    )


def _extract_planning(
    node: tree_sitter.Node,
    source: bytes,
) -> tuple[Timestamp | None, Timestamp | None, Timestamp | None]:
    """Return ``(scheduled, deadline, closed)`` planning timestamps."""
    planning_node = node.child_by_field_name("planning")
    if planning_node is None or planning_node.type != _PLANNING:
        return None, None, None

    scheduled: Timestamp | None = None
    deadline: Timestamp | None = None
    closed: Timestamp | None = None
    current_keyword: str | None = None

    for child in planning_node.named_children:
        if child.type == _PLANNING_KEYWORD:
            current_keyword = source[child.start_byte : child.end_byte].decode().upper()
            continue
        if child.type != _TIMESTAMP or current_keyword is None:
            continue

        timestamp = Timestamp.from_node(child, source)
        if current_keyword == "SCHEDULED":
            scheduled = timestamp
        elif current_keyword == "DEADLINE":
            deadline = timestamp
        elif current_keyword == "CLOSED":
            closed = timestamp

    return scheduled, deadline, closed


def _find_first_subheading(node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Return the first direct sub-heading node, if present."""
    for child in node.children:
        if child.type == _HEADING:
            return child
    return None


def _render_heading_dirty(heading: Heading) -> str:
    """Render a dirty heading from semantic fields only."""
    line_parts: list[str] = ["*" * heading.level]

    if heading.todo:
        line_parts.append(heading.todo)

    if heading.priority:
        line_parts.append(f"[#{heading.priority}]")

    if heading.title is not None:
        line_parts.append(str(heading.title))

    headline = " ".join(line_parts)

    if heading.tags:
        headline = f"{headline} :{':'.join(heading.tags)}:"

    parts = [f"{headline}\n"]
    planning_entries: list[str] = []
    if heading.scheduled is not None:
        planning_entries.append(f"SCHEDULED: {heading.scheduled}")
    if heading.deadline is not None:
        planning_entries.append(f"DEADLINE: {heading.deadline}")
    if heading.closed is not None:
        planning_entries.append(f"CLOSED: {heading.closed}")
    if planning_entries:
        parts.append(f"{' '.join(planning_entries)}\n")

    if heading.properties is not None:
        parts.append(str(heading.properties))
    if heading.logbook is not None:
        parts.append(str(heading.logbook))

    parts.extend(str(element) for element in heading.body)
    return "".join(parts)
