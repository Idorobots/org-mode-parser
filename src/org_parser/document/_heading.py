"""Implementation of :class:`Heading` — an Org Mode heading / sub-heading."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._element import Element
from org_parser.text._inline import CompletionCounter
from org_parser.text._rich_text import RichText

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document

__all__ = ["Heading"]

# Node type names produced by the tree-sitter grammar.
_HEADING = "heading"
_COMPLETION_COUNTER = "completion_counter"
_TAG = "tag"


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
        self._body: list[Element] = body if body is not None else []
        self._children: list[Heading] = children if children is not None else []
        self._node: tree_sitter.Node | None = None
        self._dirty = False

    # -- factory method ------------------------------------------------------

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        *,
        document: Document,
        parent: Heading | Document,
        source: bytes,
    ) -> Heading:
        """Build a :class:`Heading` (and its sub-tree) from a tree-sitter node.

        Args:
            node: A tree-sitter node of type ``heading``.
            document: The root document that contains this heading.
            parent: The parent :class:`Heading` or :class:`Document`.
            source: The full source bytes of the document.

        Returns:
            A fully populated :class:`Heading` with recursively built
            children.
        """
        level = _extract_level(node)
        todo = _extract_todo(node)
        priority = _extract_priority(node)
        title_nodes = node.children_by_field_name("title")
        title = RichText.from_nodes(title_nodes, source)
        counter = _extract_counter(title_nodes)
        tags = _extract_tags(node)
        body = _extract_body(node, source)

        heading = cls(
            level=level,
            document=document,
            parent=parent,
            todo=todo,
            priority=priority,
            title=title,
            counter=counter,
            tags=tags,
            body=body,
        )
        heading._node = node

        # Recursively build sub-headings.
        for child in node.children:
            if child.type == _HEADING:
                sub = cls.from_node(
                    child,
                    document=document,
                    parent=heading,
                    source=source,
                )
                heading._children.append(sub)

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
        self._mark_dirty()

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
    def body(self) -> list[Element]:
        """Body elements (excludes sub-headings)."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set body elements and mark this heading as dirty."""
        self._body = value
        self._mark_dirty()

    @property
    def parent(self) -> Heading | Document:
        """The parent :class:`Heading` or :class:`Document`."""
        return self._parent

    @parent.setter
    def parent(self, value: Heading | Document) -> None:
        """Set the parent reference and mark this heading as dirty."""
        self._parent = value
        self._mark_dirty()

    @property
    def children(self) -> list[Heading]:
        """Direct sub-headings."""
        return self._children

    @children.setter
    def children(self, value: list[Heading]) -> None:
        """Set direct sub-headings and mark this heading as dirty."""
        self._children = value
        self._mark_dirty()

    @property
    def dirty(self) -> bool:
        """Whether this heading has been mutated after creation."""
        return self._dirty

    def _mark_dirty(self) -> None:
        """Mark this heading and its document as dirty."""
        self._dirty = True
        self._document.mark_dirty()

    def mark_dirty(self) -> None:
        """Mark this heading and its document as dirty."""
        self._mark_dirty()

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
        """Return a developer-friendly representation."""
        stars = "*" * self._level
        title = str(self._title) if self._title else ""
        return f"Heading({stars} {title!r})"


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
    source: bytes,
) -> list[Element]:
    """Return :class:`Element` instances for each child of the body section."""
    section_node = node.child_by_field_name("body")
    if section_node is None:
        return []
    return [Element.from_node(child, source) for child in section_node.named_children]


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
    parts.extend(str(element) for element in heading.body)
    return "".join(parts)
