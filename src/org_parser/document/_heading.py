"""Implementation of [org_parser.document.Heading][] — an Org Mode heading / sub-heading."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
    Indent,
    List,
    ListItem,
    Logbook,
    Properties,
    Repeat,
)
from org_parser.element._dirty_list import DirtyList
from org_parser.element._element import (
    Element,
    build_semantic_repr,
    coerce_element_body,
    element_from_error_or_unknown,
    ensure_trailing_newline,
)
from org_parser.element._structure_recovery import (
    attach_affiliated_keywords,
)
from org_parser.text._inline import CompletionCounter
from org_parser.text._rich_text import RichText, coerce_optional_rich_text, coerce_rich_text
from org_parser.time import Clock, Timestamp

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    import tree_sitter

    from org_parser.document._document import Document

__all__ = ["Heading", "ensure_child_heading_level", "shift_heading_subtree"]


class Heading:
    """An Org Mode heading (or sub-heading).

    A heading exposes the parsed components of an Org headline — stars, TODO
    state, priority cookie, title text, tags, completion counter — as well as
    the body elements and any nested sub-headings.

    Args:
        level: The heading level (count of leading ``*`` characters).
        document: The root [org_parser.document.Document][] that contains this heading.
        parent: The parent [org_parser.document.Heading][] or [org_parser.document.Document][].
        todo: The TODO keyword (e.g. ``"TODO"``, ``"DONE"``), or *None*.
        is_comment: Whether this heading uses the ``COMMENT`` marker.
        priority: The priority letter or number (e.g. ``"A"``, ``"1"``), or
            *None*.
        title: The heading title as [org_parser.text.RichText][], or *None*.
        counter: Completion counter object (e.g. ``[1/3]``), or *None*.
        heading_tags: A list of tag strings found on this heading line in source order.
        repeats: Repeated task entries extracted from ``LOGBOOK`` and heading body.
        clock_entries: Clock entries extracted from ``LOGBOOK`` and heading body.
        body: Body elements of the heading (excludes sub-headings).
        children: Direct sub-headings of this heading.

    Example:
    ```python
    >>> from org_parser import loads
    >>> heading = loads("* TODO Heading 1").children[0]
    >>> heading.title_text
    'Heading 1'
    >>> heading.todo
    'TODO'
    ```
    """

    def __init__(
        self,
        *,
        level: int,
        document: Document,
        parent: Heading | Document,
        todo: str | None = None,
        is_comment: bool = False,
        priority: str | None = None,
        title: RichText | str | None = None,
        counter: CompletionCounter | None = None,
        heading_tags: Sequence[str] = (),
        scheduled: Timestamp | None = None,
        closed: Timestamp | None = None,
        deadline: Timestamp | None = None,
        properties: Properties | None = None,
        logbook: Logbook | None = None,
        repeats: Sequence[Repeat] = (),
        clock_entries: Sequence[Clock] = (),
        body: Sequence[Element] = (),
        children: Sequence[Heading] = (),
    ) -> None:
        self._level = level
        self._document = document
        self._parent = parent
        self._todo = todo
        self._is_comment = is_comment
        self._priority = priority
        self._title = coerce_optional_rich_text(title)
        self._counter = counter
        self._heading_tags: list[str] = list(heading_tags)
        self._scheduled = scheduled
        self._closed = closed
        self._deadline = deadline
        self._properties = properties if properties is not None else Properties()
        self._logbook = logbook if logbook is not None else Logbook()
        self._repeats: list[Repeat] = list(repeats)
        self._clock_entries: list[Clock] = list(clock_entries)
        self._body: list[Element] = list(body)
        self._children: list[Heading] = list(children)
        self._node: tree_sitter.Node | None = None
        self._dirty = False

        self._adopt_element(self._title)
        self._adopt_timestamp(self._scheduled)
        self._adopt_timestamp(self._closed)
        self._adopt_timestamp(self._deadline)

        self._adopt_element(self._properties)
        self._adopt_element(self._logbook)
        self._adopt_elements(self._body)
        self._adopt_elements(self._children)
        self._sync_logbook_entries()

    # -- factory method ------------------------------------------------------

    @classmethod
    def from_source(cls, source: str) -> Heading:
        """Build one heading from Org source text.

        The source must parse to exactly one top-level heading and no other
        zeroth-section semantic content.

        Args:
            source: Org source text containing exactly one heading.

        Returns:
            The parsed [org_parser.document.Heading][].

        Raises:
            ValueError: If parsing fails or the structure is not one heading.

        Example:
        ```python
        >>> from org_parser.document import Heading
        >>> heading = Heading.from_source("* TODO Heading 1")
        >>> heading.title_text
        'Heading 1'
        ```
        """
        from org_parser._from_source import parse_source_with_extractor

        heading, _ = parse_source_with_extractor(
            source,
            extractor=_extract_single_heading_node,
        )
        return heading

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        *,
        document: Document,
        parent: Heading | Document,
    ) -> Heading:
        """Build a [org_parser.document.Heading][] (and its sub-tree) from a tree-sitter node.

        Args:
            node: A tree-sitter node of type ``heading``.
            document: The root document that contains this heading.
            parent: The parent [org_parser.document.Heading][] or [org_parser.document.Document][].

        Returns:
            A fully populated [org_parser.document.Heading][] with recursively built
            children.
        """
        level = _extract_level(node, document)
        todo = _extract_todo(node, document)
        is_comment = _extract_is_comment(node)
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
            is_comment=is_comment,
            priority=priority,
            title=title,
            counter=counter,
            heading_tags=tags,
            scheduled=scheduled,
            deadline=deadline,
            closed=closed,
            body=[],
        )
        heading._node = node

        properties, logbook, body = _extract_body(
            node,
            parent=heading,
            document=document,
        )
        heading._properties = properties if properties is not None else Properties(parent=heading)
        heading._logbook = logbook if logbook is not None else Logbook(parent=heading)
        heading._adopt_element(heading._properties)
        heading._adopt_element(heading._logbook)
        heading._body = body
        heading._sync_logbook_entries()

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
        """The [org_parser.document.Document][] that ultimately contains this heading.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads("* TODO Heading 1")
        >>> heading = documentt.children[0]
        >>> heading.title_text
        'Heading 1'
        >>> heading.document is document
        True
        ```
        """
        return self._document

    @document.setter
    def document(self, value: Document) -> None:
        """Set the owning document."""
        self._document = value
        self._dirty = True
        self._parent.mark_dirty()
        value.mark_dirty()

    @property
    def level(self) -> int:
        """The heading level (count of leading ``*`` characters).

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads("* TODO Heading 1").children[0]
        >>> heading.heading_text
        '* TODO Heading 1'
        >>> heading.level = 3
        >>> heading.heading_text
        '*** TODO Heading 1'
        ```
        """
        return self._level

    @level.setter
    def level(self, value: int) -> None:
        """Set the heading level."""
        self._level = value
        self.mark_dirty()

    @property
    def todo(self) -> str | None:
        """The TODO keyword, or *None* if absent.

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads("* TODO Heading 1").children[0]
        >>> heading.title_text
        'Heading 1'
        >>> heading.todo = "DONE"
        >>> heading.todo
        'DONE'
        ```
        """
        return self._todo

    @todo.setter
    def todo(self, value: str | None) -> None:
        """Set the TODO keyword."""
        self._todo = value
        self.mark_dirty()

    @property
    def priority(self) -> str | None:
        """The priority value (e.g. ``"A"``, ``"1"``), or *None*.

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads("* Heading 1").children[0]
        >>> heading.heading_text
        '* Heading 1'
        >>> heading.priority = "A"
        >>> heading.heading_text
        '* [#A] Heading 1'
        ```
        """
        return self._priority

    @priority.setter
    def priority(self, value: str | None) -> None:
        """Set the priority value."""
        self._priority = value
        self.mark_dirty()

    @property
    def is_comment(self) -> bool:
        """Whether this heading is marked with the ``COMMENT`` keyword.

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads("* Heading 1").children[0]
        >>> heading.heading_text
        '* Heading 1'
        >>> heading.is_comment = True
        >>> heading.heading_text
        '* COMMENT Heading 1'
        ```
        """
        return self._is_comment

    @is_comment.setter
    def is_comment(self, value: bool) -> None:
        """Set heading ``COMMENT`` marker state."""
        self._is_comment = value
        self.mark_dirty()

    @property
    def title(self) -> RichText | None:
        """The heading title as [org_parser.text.RichText][], or *None*.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> from org_parser import loads
        >>> heading = loads("* TODO Heading 1").children[0]
        >>> heading.title_text
        'Heading 1'
        >>> heading.title = RichText("Updated")
        >>> heading.title_text
        'Updated'
        >>> heading.todo
        'TODO'
        ```
        """
        return self._title

    @title.setter
    def title(self, value: RichText | str | None) -> None:
        """Set the heading title."""
        self._title = coerce_optional_rich_text(value)
        self._adopt_element(self._title)
        self.mark_dirty()

    @property
    def counter(self) -> CompletionCounter | None:
        """The completion counter object, or *None* if absent.

        Example:
        ```python
        >>> from org_parser import loads
        >>> from org_parser.text import CompletionCounter
        >>> heading = loads("* Heading 1").children[0]
        >>> print(str(heading))
        * Heading 1
        >>> heading.counter = CompletionCounter("1/2")
        >>> print(str(heading))
        * [1/2] Heading 1
        ```
        """
        return self._counter

    @counter.setter
    def counter(self, value: CompletionCounter | None) -> None:
        """Set the completion counter."""
        self._counter = value
        self.mark_dirty()

    @property
    def heading_tags(self) -> list[str]:
        """Tag strings found on this heading line, in source order.

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads("* TODO Heading 1").children[0]
        >>> heading.heading_tags = ["work", "docs"]
        >>> heading.heading_tags
        ['work', 'docs']
        ```
        """

        def on_heading_tags_mutation(wrapped: DirtyList[str]) -> None:
            self._heading_tags = list(wrapped)
            self.mark_dirty()

        return DirtyList(self._heading_tags, on_mutation=on_heading_tags_mutation)

    @heading_tags.setter
    def heading_tags(self, value: list[str]) -> None:
        """Set tag strings on this heading line."""
        self._heading_tags = list(value)
        self.mark_dirty()

    @property
    def tags(self) -> list[str]:
        """All effective tags inherited from FILETAGS and ancestor headings.

        Returns document FILETAGS, then each ancestor's ``heading_tags``
        (outermost first), then this heading's own ``heading_tags``.
        Duplicates are removed; the first occurrence is kept.

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads('''
        ... #+FILETAGS: :tag1:
        ... * TODO Heading 1    :tag2:
        ... ''').children[0]
        >>> heading.heading_tags
        ['tag2']
        >>> heading.tags
        ['tag1', 'tag2']
        ```
        """
        result: list[str] = []
        seen: set[str] = set()
        for tag in [*self._parent.tags, *self._heading_tags]:
            if tag in seen:
                continue
            seen.add(tag)
            result.append(tag)
        return result

    @property
    def heading_category(self) -> RichText | None:
        """The ``CATEGORY`` value from this heading's own ``PROPERTIES`` drawer.

        Returns the [org_parser.text.RichText][] value of the ``CATEGORY`` node property
        when the heading has a ``PROPERTIES`` drawer containing that key, or
        *None* otherwise.  Use [org_parser.document.Heading.category][] to get the fully-inherited
        effective category.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> from org_parser import loads
        >>> heading = loads('''
        ... #+CATEGORY: Category
        ... * TODO Heading 1
        ... :PROPERTIES:
        ... :CATEGORY: Heading
        ... :END:
        ... ''').children[0]
        >>> heading.heading_category
        'Heading'
        ```
        """
        if "CATEGORY" in self._properties:
            category = self._properties["CATEGORY"]
            if isinstance(category, RichText):
                return category
            return coerce_rich_text(str(category))
        return None

    @heading_category.setter
    def heading_category(self, value: RichText | str | None) -> None:
        """Set or clear the ``CATEGORY`` property in this heading's ``PROPERTIES``.

        When *value* is not *None* the ``CATEGORY`` key is created or updated
        inside the heading's ``PROPERTIES`` drawer, creating the drawer when it
        does not yet exist.  When *value* is *None* the key is removed from the
        drawer; if the key was absent the call is a no-op and does **not** mark
        the heading dirty.
        """
        if value is None:
            if "CATEGORY" in self._properties:
                del self._properties["CATEGORY"]
                self.mark_dirty()
            return
        self._properties["CATEGORY"] = coerce_rich_text(value)
        self.mark_dirty()

    @property
    def category(self) -> RichText | None:
        """The effective category for this heading.

        Returns [org_parser.document.Heading.heading_category][] when it is set
        on this heading's own ``PROPERTIES`` drawer.  Otherwise the value is
        inherited from the parent [org_parser.document.Heading][] or
        [org_parser.document.Document][], walking up the tree until a category
        is found or the document level is reached.

        Example:
        ```python
        >>> from org_parser.text import RichText
        >>> from org_parser import loads
        >>> heading = loads('''
        ... #+CATEGORY: Category
        ... * TODO Heading 1
        ... ''').children[0]
        >>> heading.heading_category
        None
        >>> heading.category
        'Category'
        ```
        """
        own = self.heading_category
        if own is not None:
            return own
        return self._parent.category

    @property
    def id(self) -> str | None:
        """The ``ID`` value from this heading's ``PROPERTIES`` drawer.

        Returns ``None`` when no ``ID`` entry exists or when it renders to an
        empty string.
        """
        if "ID" not in self._properties:
            return None
        heading_id = str(self._properties["ID"])
        return heading_id if heading_id != "" else None

    @id.setter
    def id(self, value: RichText | str | None) -> None:
        """Set or clear this heading's ``ID`` property value."""
        if value is None:
            if "ID" in self._properties:
                del self._properties["ID"]
                self._sync_document_heading_id_index()
                self.mark_dirty()
            return

        self._properties["ID"] = coerce_rich_text(value)
        self._sync_document_heading_id_index()
        self.mark_dirty()

    @property
    def scheduled(self) -> Timestamp | None:
        """The ``SCHEDULED`` planning timestamp, or *None*.

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads('''
        ... * Heading 1
        ... SCHEDULED: <2026-03-29>
        ...''').children[0]
        >>> heading.scheduled.start.year
        2026
        ```
        """
        return self._scheduled

    @scheduled.setter
    def scheduled(self, value: Timestamp | None) -> None:
        """Set the ``SCHEDULED`` planning timestamp."""
        self._set_planning_timestamp(SCHEDULED, value)

    @property
    def closed(self) -> Timestamp | None:
        """The ``CLOSED`` planning timestamp, or *None*.

        Example:
        ```python
        >>> from org_parser.time import Timestamp
        >>> from org_parser import loads
        >>> heading = loads("* Heading 1").children[0]
        >>> heading.closed = Timestamp.from_source("<2026-03-29 Sun>")
        >>> heading.closed.start.year
        2026
        ```
        """
        return self._closed

    @closed.setter
    def closed(self, value: Timestamp | None) -> None:
        """Set the ``CLOSED`` planning timestamp."""
        self._set_planning_timestamp(CLOSED, value)

    @property
    def deadline(self) -> Timestamp | None:
        """The ``DEADLINE`` planning timestamp, or *None*.

        Example:
        ```python
        >>> from org_parser.time import Timestamp
        >>> from org_parser import loads
        >>> heading = loads("* Heading 1").children[0]
        >>> heading.deadline = Timestamp.from_source("<2026-03-29 Sun 18:00 -5d>")
        >>> heading.deadline.start.year
        2026
        ```
        """
        return self._deadline

    @deadline.setter
    def deadline(self, value: Timestamp | None) -> None:
        """Set the ``DEADLINE`` planning timestamp."""
        self._set_planning_timestamp(DEADLINE, value)

    @property
    def body(self) -> list[Element]:
        """Body elements (excludes sub-headings).

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads("* TODO Heading 1").children[0]
        >>> heading.body = [Paragraph.from_source("Add some body text")]
        >>> print(str(heading))
        * TODO Heading 1
        Add some body text
        ```
        """

        def on_body_mutation(wrapped: DirtyList[Element]) -> None:
            self._body = list(wrapped)
            self._adopt_elements(self._body)
            self._sync_logbook_entries()
            self.mark_dirty()

        return DirtyList(self._body, on_mutation=on_body_mutation)

    @body.setter
    def body(self, value: Sequence[Element] | Element | str) -> None:
        """Set body elements."""
        self._body = list(coerce_element_body(value))
        self._adopt_elements(self._body)
        self._sync_logbook_entries()
        self.mark_dirty()

    @property
    def properties(self) -> Properties:
        """Merged heading ``PROPERTIES`` drawer.

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads("* TODO Heading 1").children[0]
        >>> heading.properties["key"] = RichText("Value")
        >>> print(str(heading))
        * TODO Heading 1
        :PROPERTIES:
        :key: Value
        :END:
        ```
        """
        return self._properties

    @properties.setter
    def properties(self, value: Properties | dict[str, Any] | None) -> None:
        """Set merged heading ``PROPERTIES`` drawer.

        Assigning ``None`` resets this to an empty drawer instance.
        """
        if value is None:
            properties = Properties(parent=self)
        elif isinstance(value, Properties):
            properties = value
        else:
            properties = Properties(properties=value, parent=self)
        self._properties = properties
        self._adopt_element(self._properties)
        self.mark_dirty()

    @property
    def logbook(self) -> Logbook:
        """Merged heading ``LOGBOOK`` drawer.

        Example:
        ```python
        >>> from org_parser import loads
        >>> from org_parser.element import Repeat
        >>> from org_parser.time import Clock, Timestamp
        >>> heading = loads("* TODO Heading 1").children[0]
        >>> heading.logbook.clock_entries = [Clock.from_source("CLOCK: [2025-10-10]")]
        >>> ts = Timestamp.from_source("<2025-10-10>")
        >>> heading.logbook.repeats = [Repeat(after="DONE", before="TODO", timestamp=ts)]
        >>> print(str(heading))
        * TODO Heading 1
        :LOGBOOK:
        CLOCK: [2025-10-10]
        - State "DONE"       from "TODO"       <2025-10-10>
        :END:
        ```
        """
        return self._logbook

    @logbook.setter
    def logbook(self, value: Logbook | None) -> None:
        """Set merged heading ``LOGBOOK`` drawer.

        Assigning ``None`` resets this to an empty drawer instance.
        """
        self._logbook = value if value is not None else Logbook(parent=self)
        self._adopt_element(self._logbook)
        self._sync_logbook_entries()
        self.mark_dirty()

    @property
    def repeats(self) -> list[Repeat]:
        """Repeated task entries from this heading's logbook and body.

        Example:
        ```python
        >>> from org_parser import loads
        >>> from org_parser.element import Repeat
        >>> from org_parser.time import Timestamp
        >>> heading = loads("* TODO Heading 1").children[0]
        >>> ts = Timestamp.from_source("<2025-10-10>")
        >>> heading.repeats = [Repeat(after="DONE", before="TODO", timestamp=ts)]
        >>> print(str(heading))
        * TODO Heading 1
        :LOGBOOK:
        - State "DONE"       from "TODO"       <2025-10-10>
        :END:
        ```
        """

        def on_repeats_mutation(wrapped: DirtyList[Repeat]) -> None:
            self._promote_body_logbook_entries_into_logbook()
            self._repeats = list(wrapped)
            logbook = self._logbook
            logbook.repeats = self._repeats
            self._sync_logbook_entries()
            self.mark_dirty()

        return DirtyList(self._repeats, on_mutation=on_repeats_mutation)

    @repeats.setter
    def repeats(self, value: list[Repeat]) -> None:
        """Set repeats and synchronize them into the logbook drawer."""
        self._promote_body_logbook_entries_into_logbook()
        self._repeats = list(value)
        logbook = self._logbook
        logbook.repeats = self._repeats
        self._sync_logbook_entries()
        self.mark_dirty()

    def add_repeat(self, repeat: Repeat) -> None:
        """Append one repeat and synchronize it into the logbook.

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
        self._promote_body_logbook_entries_into_logbook()
        self._repeats = [*self._repeats, repeat]
        logbook = self._logbook
        logbook.repeats = [*logbook.repeats, repeat]
        self._sync_logbook_entries()
        self.mark_dirty()

    @property
    def clock_entries(self) -> list[Clock]:
        """Clock entries from this heading's logbook and body.

        Example:
        ```python
        >>> from org_parser import loads
        >>> from org_parser.time import Clock
        >>> heading = loads("* TODO Heading 1").children[0]
        >>> heading.clock_entries = [Clock.from_source("CLOCK: [2025-10-10]")]
        >>> print(str(heading))
        * TODO Heading 1
        :LOGBOOK:
        CLOCK: [2025-10-10]
        :END:
        ```
        """

        def on_clock_entries_mutation(wrapped: DirtyList[Clock]) -> None:
            self._promote_body_logbook_entries_into_logbook()
            self._clock_entries = list(wrapped)
            logbook = self._logbook
            logbook.clock_entries = self._clock_entries
            self._sync_logbook_entries()
            self.mark_dirty()

        return DirtyList(self._clock_entries, on_mutation=on_clock_entries_mutation)

    @clock_entries.setter
    def clock_entries(self, value: list[Clock]) -> None:
        """Set clock entries and synchronize them into the logbook drawer."""
        self._promote_body_logbook_entries_into_logbook()
        self._clock_entries = list(value)
        logbook = self._logbook
        logbook.clock_entries = self._clock_entries
        self._sync_logbook_entries()
        self.mark_dirty()

    @property
    def parent(self) -> Heading | Document:
        """The parent [org_parser.document.Heading][] or [org_parser.document.Document][].

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... * Heading 1
        ... ** Heading 2
        ... ''')
        >>> document[1].parent.title_text
        'Heading 1'
        ```
        """
        return self._parent

    @parent.setter
    def parent(self, value: Heading | Document) -> None:
        """Set the parent reference without changing dirty state."""
        self._parent = value

    @property
    def children(self) -> list[Heading]:
        """Direct sub-headings.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... * Heading 1
        ... ** Heading 2
        ... ''')
        >>> document[0].children[0].title_text
        'Heading 2'
        ```
        """

        def on_children_mutation(wrapped: DirtyList[Heading]) -> None:
            self._children = list(wrapped)
            self._adopt_elements(self._children)
            for child in self._children:
                ensure_child_heading_level(child, parent_level=self._level)
            self._sync_document_heading_id_index()
            self.mark_dirty()

        return DirtyList(self._children, on_mutation=on_children_mutation)

    @children.setter
    def children(self, value: list[Heading]) -> None:
        """Set direct sub-headings, adjust levels,.

        Each supplied child heading is adopted (parent set to ``self``) and
        then checked: if its [org_parser.document.Heading.level][] is not strictly greater than
        ``self.level`` it is shifted — along with its entire descendant
        subtree — so that the invariant ``child.level > self.level`` holds.
        Only headings whose level is actually changed are marked dirty.
        """
        self._children = list(value)
        self._adopt_elements(self._children)
        for child in self._children:
            ensure_child_heading_level(child, parent_level=self._level)
        self._sync_document_heading_id_index()
        self.mark_dirty()

    @property
    def is_root(self) -> bool:
        """Whether this heading is the root node of a document tree.

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads("* TODO Heading 1").children[0]
        >>> heading.is_root
        False
        ```
        """
        return False

    @property
    def is_leaf(self) -> bool:
        """Whether this heading has no direct sub-headings.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... * Heading 1
        ... ** Heading 2
        ... ''')
        >>> document[0].is_leaf
        False
        >>> document[1].is_leaf
        True
        ```
        """
        return not self._children

    @property
    def is_completed(self) -> bool:
        """Whether this heading's current TODO state is a done state.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... #+TODO: TODO WAITING | DONE
        ... * TODO Heading 1
        ... ** WAITING Heading 2
        ... ** DONE Heading 3
        ... ''')
        >>> document[0].is_completed
        False
        >>> document[1].is_completed
        False
        >>> document[2].is_completed
        True
        ```
        """
        return self._todo is not None and self._todo in self._document.done_states

    @property
    def has_timestamp(self) -> bool:
        """Whether this heading has any planning, repeat, or clock timestamp.

        Example:
        ```python
        >>> document = loads('''
        ... * Heading 1
        ... ** Heading 2
        ... SCHEDULED: <2026-03-29>
        ... ''')
        >>> document[0].has_timestamp
        False
        >>> document[1].has_timestamp
        True
        ```
        """
        return bool(self.timestamps)

    @property
    def timestamps(self) -> list[Timestamp]:
        """All timestamps attached to this heading's planning and logbook data.

        Example:
        ```python
        >>> document = loads('''
        ... * Heading 1
        ... ** Heading 2
        ... SCHEDULED: <2026-03-29>
        ... ''')
        >>> document[0].timestamps
        []
        >>> len(document[1].timestamps)
        1
        ```
        """
        collected: list[Timestamp] = []
        collected.extend(
            planning
            for planning in (self._scheduled, self._closed, self._deadline)
            if planning is not None
        )
        collected.extend(repeat.timestamp for repeat in self._repeats)
        collected.extend(
            clock.timestamp for clock in self._clock_entries if clock.timestamp is not None
        )
        return collected

    @property
    def latest_timestamp(self) -> Timestamp | None:
        """Latest timestamp across planning values and logbook-derived timestamps.

        Example:
        ```python
        >>> document = loads('''
        ... * Heading 1
        ... SCHEDULED: <2026-03-29>
        ... ''')
        >>> document[0].latest_timestamp is document[0].scheduled
        True
        ```
        """
        values = self.timestamps
        if not values:
            return None
        return max(
            values,
            key=lambda timestamp: timestamp.end if timestamp.end else timestamp.start,
        )

    @property
    def earliest_timestamp(self) -> Timestamp | None:
        """Earliest timestamp across planning values and logbook-derived timestamps.

        Example:
        ```python
        >>> document = loads('''
        ... * Heading 1
        ... CLOSED: <2026-03-29>
        ... DEADLINE: <2026-03-10>
        ... ''')
        >>> document[0].earliest_timestamp is document[0].closed
        False
        ```
        """
        values = self.timestamps
        if not values:
            return None
        return min(values, key=lambda timestamp: timestamp.start)

    @property
    def body_text(self) -> str:
        """Stringified text for all body elements of this heading."""
        return "".join(str(element) for element in self._body)

    @property
    def title_text(self) -> str:
        """Stringified text for this heading's title object."""
        return "" if self._title is None else str(self._title)

    @property
    def heading_text(self) -> str:
        """Stringified heading line including stars and line-level fields.

        Example:
        ```python
        >>> from org_parser import loads
        >>> heading = loads("* TODO Heading 1  :tag:").children[0]
        >>> heading.title_text
        'Heading 1'
        >>> heading.heading_text
        '* TODO Heading 1  :tag:'
        ```
        """
        rendered = str(self)
        first_line, _, _ = rendered.partition("\n")
        return first_line

    @property
    def dirty(self) -> bool:
        """Whether this heading has been mutated after creation."""
        return self._dirty

    @property
    def line(self) -> int | None:
        """Zero-based source line of this heading's parse node, or *None*."""
        if self._node is None:
            return None
        return self._node.start_point.row

    @property
    def column(self) -> int | None:
        """Zero-based source column of this heading's parse node, or *None*."""
        if self._node is None:
            return None
        return self._node.start_point.column

    def mark_dirty(self) -> None:
        """Mark this heading dirty and bubble to its parent chain.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... * Heading 1
        ... CLOSED: <2025-10-10>
        ... SCHEDULED: <2025-10-10>
        ... ''')
        >>> document[0].mark_dirty()
        >>> print(document.render())
        * Heading 1
        SCHEDULED: <2025-10-10> CLOSED: <2025-10-10>
        ```
        """
        if self._dirty:
            return
        self._dirty = True
        self._parent.mark_dirty()

    def reformat(self) -> None:
        """Reformat heading descendants and this heading.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... * Heading 1
        ... ** Heading 2
        ... CLOSED: <2025-10-10>
        ... SCHEDULED: <2025-10-10>
        ... ''')
        >>> document[0].reformat()
        >>> print(document.render())
        * Heading 1
        ** Heading 2
        SCHEDULED: <2025-10-10> CLOSED: <2025-10-10>
        ```
        """
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
        self._properties.reformat()
        self._logbook.reformat()
        for repeat in self._repeats:
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

    def _sync_logbook_entries(self) -> None:
        """Synchronize repeat and clock caches from heading logbook and body."""
        body_repeats, body_clocks = _collect_heading_body_repeats_and_clocks(
            self._body,
            document=self._document,
        )

        self._repeats = [*self._logbook.repeats, *body_repeats]
        self._clock_entries = [*self._logbook.clock_entries, *body_clocks]

        # NOTE Attach the document for state comparisons of programmatically created repeats.
        for repeat in self._repeats:
            repeat.attach_document(self._document)

    def _promote_body_logbook_entries_into_logbook(self) -> None:
        """Move body-derived repeats/clocks into the canonical heading logbook."""
        body_repeats, body_clocks = _collect_heading_body_repeats_and_clocks(
            self._body,
            document=self._document,
        )
        if not body_repeats and not body_clocks:
            return

        cleaned_body, changed = _remove_promotable_logbook_entries_from_elements(self._body)
        if changed:
            self._body = cleaned_body
            self._adopt_elements(self._body)

        existing_repeat_ids = {id(repeat) for repeat in self._logbook.repeats}
        promoted_repeats = [
            repeat for repeat in body_repeats if id(repeat) not in existing_repeat_ids
        ]
        if promoted_repeats:
            self._logbook.repeats = [*self._logbook.repeats, *promoted_repeats]

        existing_clock_ids = {id(clock) for clock in self._logbook.clock_entries}
        promoted_clocks = [clock for clock in body_clocks if id(clock) not in existing_clock_ids]
        if promoted_clocks:
            self._logbook.clock_entries = [*self._logbook.clock_entries, *promoted_clocks]

        self._sync_logbook_entries()

    def _set_planning_timestamp(
        self,
        planning_keyword: str,
        value: Timestamp | None,
    ) -> None:
        """Set one planning timestamp field."""
        if planning_keyword == SCHEDULED:
            self._scheduled = value
            self._adopt_timestamp(self._scheduled)
        elif planning_keyword == DEADLINE:
            self._deadline = value
            self._adopt_timestamp(self._deadline)
        elif planning_keyword == CLOSED:
            self._closed = value
            self._adopt_timestamp(self._closed)
        else:
            raise ValueError(f"Unknown planning keyword: {planning_keyword!r}")
        self.mark_dirty()

    def _adopt_timestamp(self, value: Timestamp | None) -> None:
        """Attach timestamp parent ownership without changing dirty state."""
        if value is None:
            return
        value.parent = self

    def _sync_document_heading_id_index(self) -> None:
        """Rebuild this heading's document-level heading-ID index."""
        self.document.sync_heading_id_index()

    @property
    def siblings(self) -> list[Heading]:
        """Other headings at the same level under the same parent.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... * Heading 1
        ... ** Heading 2
        ... ** Heading 3
        ... ''')
        >>> document[0].siblings
        []
        >>> document[1].siblings[0].title_text
        'Heading 3'
        ```
        """
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
        return build_semantic_repr(
            "Heading",
            level=self._level,
            todo=self._todo,
            is_comment=self._is_comment if self._is_comment else None,
            priority=self._priority,
            title=self._title,
            counter=self._counter,
            scheduled=self._scheduled,
            deadline=self._deadline,
            closed=self._closed,
            properties=self._properties if _has_non_empty_properties(self._properties) else None,
            logbook=self._logbook if _has_non_empty_logbook(self._logbook) else None,
            heading_tags=self._heading_tags,
            repeats=self._repeats,
            clock_entries=self._clock_entries,
            body=self._body,
            children=self._children,
        )

    def __iter__(self) -> Iterator[Heading]:
        """Iterate over direct child headings."""
        return iter(self._children)

    def __len__(self) -> int:
        """Return number of direct child headings."""
        return len(self._children)

    def __getitem__(self, index: int | slice) -> Heading | list[Heading]:
        """Return one direct child heading (or heading slice)."""
        return self._children[index]


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


def _extract_is_comment(node: tree_sitter.Node) -> bool:
    """Return whether the heading has a ``comment`` field."""
    return node.child_by_field_name("comment") is not None


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
        properties_drawers.append(Properties.from_node(properties_node, document, parent=parent))

    section_node = node.child_by_field_name("body")
    if section_node is None:
        return (
            merge_properties_drawers(properties_drawers, parent=parent),
            merge_logbook_drawers(logbook_drawers, parent=parent),
            body,
        )

    for child in section_node.named_children:
        if child.type == PROPERTY_DRAWER:
            properties_drawers.append(Properties.from_node(child, document, parent=parent))
        elif child.type == LOGBOOK_DRAWER:
            logbook_drawers.append(Logbook.from_node(child, document, parent=parent))
        elif child.type == DRAWER:
            body.append(Drawer.from_node(child, document, parent=parent))
        else:
            body.append(extract_body_element(child, parent=parent, document=document))

    attach_affiliated_keywords(body)
    return (
        merge_properties_drawers(properties_drawers, parent=parent),
        merge_logbook_drawers(logbook_drawers, parent=parent),
        body,
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
    children = planning_node.named_children
    for index, child in enumerate(children):
        if child.type != PLANNING_KEYWORD:
            continue

        keyword = document.source_for(child).decode().upper()
        if index + 1 >= len(children):
            continue

        value_child = children[index + 1]
        if value_child.type != TIMESTAMP:
            continue

        timestamp = Timestamp.from_node(value_child, document)
        if keyword == SCHEDULED:
            scheduled = timestamp
        elif keyword == DEADLINE:
            deadline = timestamp
        elif keyword == CLOSED:
            closed = timestamp

    return scheduled, deadline, closed


def _extract_single_heading_node(
    document: Document,
) -> Heading | None:
    """Return the sole top-level heading semantic node from parsed source."""
    if (
        document.keywords
        or _has_non_empty_properties(document.properties)
        or _has_non_empty_logbook(document.logbook)
        or document.body
    ):
        return None
    if len(document.children) != 1:
        return None
    return document.children[0]


def _find_first_subheading(node: tree_sitter.Node) -> tree_sitter.Node | None:
    """Return the first direct sub-heading node, if present."""
    for child in node.children:
        if child.type == HEADING:
            return child
    return None


def _collect_heading_body_repeats_and_clocks(  # noqa: C901
    body: list[Element],
    *,
    document: Document,
) -> tuple[list[Repeat], list[Clock]]:
    """Collect repeats and clocks from heading body and nested indent blocks.

    This scans heading-level body elements and nested ``Indent`` blocks,
    including ``Logbook`` elements found in those paths. Lists are converted to
    [org_parser.element.Repeat][] where appropriate. Custom non-logbook drawer
    bodies and list-item nested bodies are intentionally ignored.
    """
    repeats: list[Repeat] = []
    clocks: list[Clock] = []

    def collect_from_list(list_element: List) -> None:
        """Recover repeat items from one heading-body plain list."""
        updated_items: list[ListItem] = []
        converted = False
        for item in list_element.items:
            converted_item: ListItem = item
            if not isinstance(item, Repeat):
                repeat = Repeat.from_list_item(item, document)
                if repeat is not None:
                    converted_item = repeat
                    converted = True
            updated_items.append(converted_item)
            if isinstance(converted_item, Repeat):
                repeats.append(converted_item)
        if converted:
            list_element.set_items(updated_items, mark_dirty=False)

    def collect_from_elements(elements: list[Element]) -> None:
        """Collect repeats and clocks from one element stream."""
        for element in elements:
            if isinstance(element, Logbook):
                repeats.extend(element.repeats)
                clocks.extend(element.clock_entries)
                continue

            if isinstance(element, Clock):
                clocks.append(element)
                continue

            if isinstance(element, List):
                collect_from_list(element)
                continue

            if isinstance(element, Indent):
                collect_from_elements(element.body)

    collect_from_elements(body)
    return repeats, clocks


def _remove_promotable_logbook_entries_from_elements(  # noqa: C901
    elements: list[Element],
) -> tuple[list[Element], bool]:
    """Remove body repeats/clocks and return ``(cleaned_elements, changed)``."""
    updated_elements: list[Element] = []
    changed = False

    for element in elements:
        if isinstance(element, Clock):
            changed = True
            continue

        if isinstance(element, List):
            kept_items = [item for item in element.items if not isinstance(item, Repeat)]
            if len(kept_items) != len(element.items):
                changed = True
                if kept_items:
                    element.set_items(kept_items, mark_dirty=False)
                    updated_elements.append(element)
                continue
            updated_elements.append(element)
            continue

        if isinstance(element, Logbook):
            cleaned_body, body_changed = _remove_promotable_logbook_entries_from_elements(
                list(element.body)
            )
            if body_changed:
                changed = True
                if cleaned_body:
                    element.body = cleaned_body
                    updated_elements.append(element)
                continue
            updated_elements.append(element)
            continue

        if isinstance(element, Indent):
            cleaned_body, body_changed = _remove_promotable_logbook_entries_from_elements(
                list(element.body)
            )
            if body_changed:
                changed = True
                if cleaned_body:
                    element.body = cleaned_body
                    updated_elements.append(element)
                continue
            updated_elements.append(element)
            continue

        updated_elements.append(element)

    return updated_elements, changed


def ensure_child_heading_level(child: Heading, *, parent_level: int) -> None:
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
    if child.level >= min_level:
        return
    delta = min_level - child.level
    shift_heading_subtree(child, delta=delta)


def shift_heading_subtree(heading: Heading, *, delta: int) -> None:
    """Add *delta* to *heading* level and all its descendants', marking each dirty.

    The parent chain of *heading* must already be set correctly before calling
    this function so that [org_parser.document.Heading.mark_dirty][] propagates through the
    right owners.

    Args:
        heading: Root of the subtree to shift.
        delta: Positive integer amount to add to every level in the subtree.
    """
    heading.level = heading.level + delta
    heading.mark_dirty()
    for child in heading.children:
        shift_heading_subtree(child, delta=delta)


def _render_heading_dirty(heading: Heading) -> str:  # noqa: C901
    """Render a dirty heading from semantic fields only."""
    line_parts: list[str] = ["*" * heading.level]
    title_text = str(heading.title) if heading.title is not None else None
    counter_text = str(heading.counter) if heading.counter is not None else None

    if heading.todo:
        line_parts.append(heading.todo)

    if heading.priority:
        line_parts.append(f"[#{heading.priority}]")

    if heading.is_comment:
        line_parts.append("COMMENT")

    if counter_text is not None and (title_text is None or counter_text not in title_text):
        line_parts.append(counter_text)

    if title_text is not None:
        line_parts.append(title_text)

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

    if _has_non_empty_properties(heading.properties):
        parts.append(ensure_trailing_newline(str(heading.properties)))
    if _has_non_empty_logbook(heading.logbook):
        parts.append(ensure_trailing_newline(str(heading.logbook)))

    parts.extend(ensure_trailing_newline(str(element)) for element in heading.body)
    return "".join(parts)


def _has_non_empty_properties(properties: Properties) -> bool:
    """Return whether a properties drawer contains at least one key."""
    return len(properties) > 0


def _has_non_empty_logbook(logbook: Logbook) -> bool:
    """Return whether a logbook drawer contains at least one body element."""
    return len(logbook) > 0
