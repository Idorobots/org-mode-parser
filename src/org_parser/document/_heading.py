"""Implementation of :class:`Heading` — an Org Mode heading / sub-heading."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import is_error_node
from org_parser._nodes import (
    CLOSED,
    COMPLETION_COUNTER,
    DEADLINE,
    DRAWER,
    HEADING,
    LOGBOOK_DRAWER,
    PLANNING,
    PLANNING_KEYWORD,
    PROPERTY_DRAWER,
    SCHEDULED,
    TAG,
    TIMESTAMP,
)
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
)
from org_parser.element._structure_recovery import (
    attach_affiliated_keywords,
    recover_lists,
)
from org_parser.text._inline import CompletionCounter
from org_parser.text._rich_text import RichText
from org_parser.time import Clock, Timestamp

if TYPE_CHECKING:
    from collections.abc import Sequence

    import tree_sitter

    from org_parser.document._document import Document

__all__ = ["Heading"]


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
        heading_tags: A list of tag strings found on this heading line in source order.
        repeated_tasks: Repeated task entries extracted from ``LOGBOOK``.
        clock_entries: Clock entries extracted from ``LOGBOOK``.
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
        heading_tags: list[str] | None = None,
        scheduled: Timestamp | None = None,
        closed: Timestamp | None = None,
        deadline: Timestamp | None = None,
        properties: Properties | None = None,
        logbook: Logbook | None = None,
        repeated_tasks: list[Repeat] | None = None,
        clock_entries: list[Clock] | None = None,
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
        self._heading_tags: list[str] = heading_tags if heading_tags is not None else []
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
        self._clock_entries: list[Clock] = (
            clock_entries
            if clock_entries is not None
            else ([] if logbook is None else logbook.clock_entries)
        )
        self._body: list[Element] = body if body is not None else []
        self._children: list[Heading] = children if children is not None else []
        self._node: tree_sitter.Node | None = None
        self._dirty = False

        self._adopt_element(self._title)

        self._adopt_element(self._properties)
        self._adopt_element(self._logbook)
        self._sync_repeated_tasks_from_logbook()
        self._sync_clock_from_logbook()
        self._adopt_elements(self._body)
        self._adopt_elements(self._children)

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
        level = _extract_level(node, document)
        todo = _extract_todo(node, document)
        priority = _extract_priority(node, document)
        title_nodes = node.children_by_field_name("title")
        title = RichText.from_nodes(title_nodes, document=document)
        counter = _extract_counter(title_nodes, document)
        tags = _extract_tags(node, document)
        scheduled, deadline, closed = _extract_planning(node, document)

        heading = cls(
            level=level,
            document=document,
            parent=parent,
            todo=todo,
            priority=priority,
            title=title,
            counter=counter,
            heading_tags=tags,
            scheduled=scheduled,
            deadline=deadline,
            closed=closed,
            properties=None,
            logbook=None,
            body=[],
        )
        heading._node = node

        properties, logbook, body = _extract_body(
            node,
            parent=heading,
            document=document,
        )
        heading._properties = properties
        heading._logbook = logbook
        heading._body = body
        heading._sync_repeated_tasks_from_logbook()
        heading._sync_clock_from_logbook()

        # Recursively build sub-headings.
        for child in node.children:
            if child.type == HEADING:
                sub = cls.from_node(
                    child,
                    document=document,
                    parent=heading,
                )
                heading._children.append(sub)
            elif is_error_node(child):
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
        self._adopt_element(self._title)
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
    def heading_tags(self) -> list[str]:
        """Tag strings found on this heading line, in source order."""
        return self._heading_tags

    @heading_tags.setter
    def heading_tags(self, value: list[str]) -> None:
        """Set tag strings on this heading line and mark it as dirty."""
        self._heading_tags = value
        self._mark_dirty()

    @property
    def tags(self) -> list[str]:
        """All effective tags inherited from FILETAGS and ancestor headings.

        Returns document FILETAGS, then each ancestor's ``heading_tags``
        (outermost first), then this heading's own ``heading_tags``.
        Duplicates are removed; the first occurrence is kept.
        """
        # Parent's tags are already fully resolved (FILETAGS + all ancestors).
        inherited = self._parent.tags
        seen = set(inherited)
        own = [t for t in self._heading_tags if t not in seen]
        return [*inherited, *own]

    @property
    def heading_category(self) -> RichText | None:
        """The ``CATEGORY`` value from this heading's own ``PROPERTIES`` drawer.

        Returns the :class:`RichText` value of the ``CATEGORY`` node property
        when the heading has a ``PROPERTIES`` drawer containing that key, or
        *None* otherwise.  Use :attr:`category` to get the fully-inherited
        effective category.
        """
        if self._properties is not None and "CATEGORY" in self._properties:
            return self._properties["CATEGORY"]
        return None

    @heading_category.setter
    def heading_category(self, value: RichText | None) -> None:
        """Set or clear the ``CATEGORY`` property in this heading's ``PROPERTIES``.

        When *value* is not *None* the ``CATEGORY`` key is created or updated
        inside the heading's ``PROPERTIES`` drawer, creating the drawer when it
        does not yet exist.  When *value* is *None* the key is removed from the
        drawer; if the key was absent the call is a no-op and does **not** mark
        the heading dirty.
        """
        if value is None:
            if self._properties is not None and "CATEGORY" in self._properties:
                del self._properties["CATEGORY"]
                self._mark_dirty()
            return
        if self._properties is None:
            self._properties = Properties(parent=self)
        self._properties["CATEGORY"] = value
        self._mark_dirty()

    @property
    def category(self) -> RichText | None:
        """The effective category for this heading.

        Returns :attr:`heading_category` when it is set on this heading's own
        ``PROPERTIES`` drawer.  Otherwise the value is inherited from the
        parent :class:`Heading` or :class:`Document`, walking up the tree
        until a category is found or the document level is reached.
        """
        own = self.heading_category
        if own is not None:
            return own
        return self._parent.category

    @property
    def scheduled(self) -> Timestamp | None:
        """The ``SCHEDULED`` planning timestamp, or *None*."""
        return self._scheduled

    @scheduled.setter
    def scheduled(self, value: Timestamp | None) -> None:
        """Set the ``SCHEDULED`` planning timestamp and mark dirty."""
        self._set_planning_timestamp(SCHEDULED, value)

    @property
    def closed(self) -> Timestamp | None:
        """The ``CLOSED`` planning timestamp, or *None*."""
        return self._closed

    @closed.setter
    def closed(self, value: Timestamp | None) -> None:
        """Set the ``CLOSED`` planning timestamp and mark dirty."""
        self._set_planning_timestamp(CLOSED, value)

    @property
    def deadline(self) -> Timestamp | None:
        """The ``DEADLINE`` planning timestamp, or *None*."""
        return self._deadline

    @deadline.setter
    def deadline(self, value: Timestamp | None) -> None:
        """Set the ``DEADLINE`` planning timestamp and mark dirty."""
        self._set_planning_timestamp(DEADLINE, value)

    @property
    def body(self) -> list[Element]:
        """Body elements (excludes sub-headings)."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set body elements and mark this heading as dirty."""
        self._body = value
        self._adopt_elements(self._body)
        self._mark_dirty()

    @property
    def properties(self) -> Properties | None:
        """Merged heading ``PROPERTIES`` drawer, or *None*."""
        return self._properties

    @properties.setter
    def properties(self, value: Properties | None) -> None:
        """Set merged heading ``PROPERTIES`` drawer and mark dirty."""
        self._properties = value
        self._adopt_element(self._properties)
        self._mark_dirty()

    @property
    def logbook(self) -> Logbook | None:
        """Merged heading ``LOGBOOK`` drawer, or *None*."""
        return self._logbook

    @logbook.setter
    def logbook(self, value: Logbook | None) -> None:
        """Set merged heading ``LOGBOOK`` drawer and mark dirty."""
        self._logbook = value
        self._adopt_element(self._logbook)
        self._sync_repeated_tasks_from_logbook()
        self._sync_clock_from_logbook()
        self._mark_dirty()

    @property
    def repeated_tasks(self) -> list[Repeat]:
        """Repeated task entries extracted from this heading's logbook."""
        return self._repeated_tasks

    @repeated_tasks.setter
    def repeated_tasks(self, value: list[Repeat]) -> None:
        """Set repeated tasks and synchronize them into the logbook drawer."""
        self._repeated_tasks = value
        logbook = self._ensure_logbook()
        logbook.repeats = self._repeated_tasks
        self._mark_dirty()

    def add_repeated_task(self, repeat: Repeat) -> None:
        """Append one repeated task and synchronize it into the logbook."""
        self._repeated_tasks = [*self._repeated_tasks, repeat]
        logbook = self._ensure_logbook()
        logbook.repeats = self._repeated_tasks
        self._mark_dirty()

    @property
    def clock_entries(self) -> list[Clock]:
        """Clock entries extracted from this heading's logbook."""
        return self._clock_entries

    @clock_entries.setter
    def clock_entries(self, value: list[Clock]) -> None:
        """Set clock entries and synchronize them into the logbook drawer."""
        self._clock_entries = value
        logbook = self._ensure_logbook()
        logbook.clock_entries = self._clock_entries
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
        """Set direct sub-headings, adjust levels, and mark this heading dirty.

        Each supplied child heading is adopted (parent set to ``self``) and
        then checked: if its :attr:`level` is not strictly greater than
        ``self.level`` it is shifted — along with its entire descendant
        subtree — so that the invariant ``child.level > self.level`` holds.
        Only headings whose level is actually changed are marked dirty.
        """
        self._children = value
        self._adopt_elements(self._children)
        for child in self._children:
            _ensure_child_heading_level(child, parent_level=self._level)
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
        if self._title is not None:
            self._title.reformat()
        if self._counter is not None:
            self._counter.reformat()
        if self._scheduled is not None:
            self._scheduled.reformat()
        if self._deadline is not None:
            self._deadline.reformat()
        if self._closed is not None:
            self._closed.reformat()
        if self._properties is not None:
            self._properties.reformat()
        if self._logbook is not None:
            self._logbook.reformat()
        for repeat in self._repeated_tasks:
            repeat.reformat()
        for clock in self._clock_entries:
            clock.reformat()
        for element in self._body:
            element.reformat()
        for child in self._children:
            child.reformat()
        self.mark_dirty()

    def _adopt_element(
        self,
        value: RichText | Properties | Logbook | Element | Heading | None,
    ) -> None:
        """Assign this heading as parent for one child semantic object."""
        if value is None:
            return
        value.parent = self

    def _adopt_elements(
        self,
        values: Sequence[RichText | Properties | Logbook | Element | Heading | None],
    ) -> None:
        """Assign this heading as parent for each provided child object."""
        for value in values:
            self._adopt_element(value)

    def _sync_repeated_tasks_from_logbook(self) -> None:
        """Synchronize local repeated-task cache from the current logbook."""
        if self._logbook is None:
            self._repeated_tasks = []
            return
        self._repeated_tasks = self._logbook.repeats

    def _sync_clock_from_logbook(self) -> None:
        """Synchronize local clock cache from the current logbook."""
        if self._logbook is None:
            self._clock_entries = []
            return
        self._clock_entries = self._logbook.clock_entries

    def _ensure_logbook(self) -> Logbook:
        """Return heading logbook, creating one when absent."""
        if self._logbook is None:
            self._logbook = Logbook(parent=self)
            self._adopt_element(self._logbook)
        return self._logbook

    def _set_planning_timestamp(
        self,
        planning_keyword: str,
        value: Timestamp | None,
    ) -> None:
        """Set one planning timestamp field and mark this heading as dirty."""
        if planning_keyword == SCHEDULED:
            self._scheduled = value
        elif planning_keyword == DEADLINE:
            self._deadline = value
        elif planning_keyword == CLOSED:
            self._closed = value
        else:
            raise ValueError(f"Unknown planning keyword: {planning_keyword!r}")
        self._mark_dirty()

    @property
    def siblings(self) -> list[Heading]:
        """Other headings at the same level under the same parent."""
        return [h for h in self._parent.children if h is not self]

    def render(self) -> str:
        """Return the complete Org Mode text for a heading including subheadings.

        For clean (unmodified) parse-backed headings the original source bytes are
        returned verbatim, preserving all whitespace and formatting.  For dirty
        headings, or heaidngs built without a backing source, the representation is
        reconstructed from their semantic fields via
        :func:`str`.

        Returns:
            Full Org Mode text including all subheadings.
        """
        if not self.dirty and self._node is not None:
            return self._document.source_for(self._node).decode()
        parts: list[str] = [str(self)]
        parts.extend(heading.render() for heading in self.children)
        return "".join(parts)

    # -- dunder protocols ----------------------------------------------------

    def __str__(self) -> str:
        """Return a textual representation of this heading and its body.

        When the heading is clean and still backed by a parse tree, this
        returns the exact source slice that spans the heading line and body
        section only, excluding any sub-headings. Once dirty, this is rebuilt
        from semantic fields.
        """
        if not self._dirty and self._node is not None:
            source = self.document.source_for(self._node)
            end_index = len(source)
            first_subheading = _find_first_subheading(self._node)
            if first_subheading is not None:
                end_index = first_subheading.start_byte - self._node.start_byte
            return source[:end_index].decode()

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
            ("heading_tags", self._heading_tags),
            ("repeated_tasks", self._repeated_tasks),
            ("clock_entries", self._clock_entries),
            ("body", self._body),
            ("children", self._children),
        ]
        parts.extend(f"{name}={value!r}" for name, value in list_parts if value)
        return f"Heading({', '.join(parts)})"


# ---------------------------------------------------------------------------
# Private helpers — field extraction from tree-sitter nodes
# ---------------------------------------------------------------------------


def _extract_level(node: tree_sitter.Node, document: Document) -> int:
    """Return the heading level from the ``stars`` field."""
    stars_node = node.child_by_field_name("stars")
    if stars_node is None:
        return 0  # pragma: no cover - defensive
    return len(document.source_for(stars_node))


def _extract_todo(node: tree_sitter.Node, document: Document) -> str | None:
    """Return the TODO keyword text, or *None*."""
    todo_node = node.child_by_field_name("todo")
    if todo_node is None:
        return None
    # The todo_keyword node includes trailing whitespace; strip it.
    return document.source_for(todo_node).decode().strip() or None


def _extract_priority(node: tree_sitter.Node, document: Document) -> str | None:
    """Return the priority value (letter or number), or *None*.

    The priority node stores its value in the ``value`` field.
    """
    prio_node = node.child_by_field_name("priority")
    if prio_node is None:
        return None
    value_node = prio_node.child_by_field_name("value")
    if value_node is None:
        return None
    return document.source_for(value_node).decode() or None


def _extract_counter(
    title_nodes: list[tree_sitter.Node],
    document: Document,
) -> CompletionCounter | None:
    """Scan title children for a ``completion_counter`` and return its inner value.

    The completion counter node stores its value in the ``value`` field.
    """
    for n in title_nodes:
        if n.type == COMPLETION_COUNTER:
            value_node = n.child_by_field_name("value")
            if value_node is None:
                continue  # pragma: no cover - defensive
            value = document.source_for(value_node).decode()
            if value == "":
                return None
            return CompletionCounter(value)
    return None


def _extract_tags(node: tree_sitter.Node, document: Document) -> list[str]:
    """Return the list of tag strings from the ``tags`` field."""
    tags_node = node.child_by_field_name("tags")
    if tags_node is None:
        return []
    return [
        document.source_for(child).decode()
        for child in tags_node.named_children
        if child.type == TAG
    ]


def _extract_body(
    node: tree_sitter.Node,
    *,
    parent: Heading | Document,
    document: Document,
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
        if child.type == PROPERTY_DRAWER:
            properties_drawers.append(
                Properties.from_node(child, document, parent=parent)
            )
        elif child.type == LOGBOOK_DRAWER:
            logbook_drawers.append(Logbook.from_node(child, document, parent=parent))
        elif child.type == DRAWER:
            body.append(Drawer.from_node(child, document, parent=parent))
        else:
            body.append(extract_body_element(child, parent=parent, document=document))

    recovered_body = recover_lists(body, parent=parent)
    attach_affiliated_keywords(recovered_body)
    return (
        merge_properties_drawers(properties_drawers, parent=parent),
        merge_logbook_drawers(logbook_drawers, parent=parent),
        recovered_body,
    )


def _extract_planning(
    node: tree_sitter.Node,
    document: Document,
) -> tuple[Timestamp | None, Timestamp | None, Timestamp | None]:
    """Return ``(scheduled, deadline, closed)`` planning timestamps."""
    planning_node = node.child_by_field_name("planning")
    if planning_node is None or planning_node.type != PLANNING:
        return None, None, None

    scheduled: Timestamp | None = None
    deadline: Timestamp | None = None
    closed: Timestamp | None = None
    current_keyword: str | None = None

    for child in planning_node.named_children:
        if child.type == PLANNING_KEYWORD:
            current_keyword = document.source_for(child).decode().upper()
            continue
        if child.type != TIMESTAMP or current_keyword is None:
            continue

        timestamp = Timestamp.from_node(child, document)
        if current_keyword == SCHEDULED:
            scheduled = timestamp
        elif current_keyword == DEADLINE:
            deadline = timestamp
        elif current_keyword == CLOSED:
            closed = timestamp

    return scheduled, deadline, closed


def _find_first_subheading(node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Return the first direct sub-heading node, if present."""
    for child in node.children:
        if child.type == HEADING:
            return child
    return None


def _ensure_child_heading_level(child: Heading, *, parent_level: int) -> None:
    """Adjust *child* level to be strictly greater than *parent_level*.

    When ``child.level > parent_level`` the heading is already valid and this
    function is a no-op (the heading is **not** marked dirty).  When
    ``child.level <= parent_level`` the entire subtree rooted at *child* is
    shifted up by ``parent_level + 1 - child.level`` so that relative level
    differences within the subtree are preserved.  Each heading whose level
    changes is marked dirty.

    Args:
        child: The heading being attached to a parent.
        parent_level: The level of the new parent heading (or 0 for a
            document, which enforces a minimum child level of 1).
    """
    min_level = parent_level + 1
    if child._level >= min_level:
        return
    delta = min_level - child._level
    _shift_heading_subtree(child, delta=delta)


def _shift_heading_subtree(heading: Heading, *, delta: int) -> None:
    """Add *delta* to *heading* level and all its descendants', marking each dirty.

    The parent chain of *heading* must already be set correctly before calling
    this function so that :meth:`Heading._mark_dirty` propagates through the
    right owners.

    Args:
        heading: Root of the subtree to shift.
        delta: Positive integer amount to add to every level in the subtree.
    """
    heading._level += delta
    heading._mark_dirty()
    for child in heading._children:
        _shift_heading_subtree(child, delta=delta)


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

    if heading.heading_tags:
        space = "" if headline.endswith(" ") else " "
        headline = f"{headline}{space}:{':'.join(heading.heading_tags)}:"

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
