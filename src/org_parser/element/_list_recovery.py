"""Semantic recovery helpers for flat list-item streams."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from org_parser.element._list import List, ListItem
from org_parser.element._paragraph import Paragraph

if TYPE_CHECKING:
    from org_parser.document._document import Document
    from org_parser.document._heading import Heading
    from org_parser.element._element import Element

__all__ = ["recover_lists"]


@dataclass(slots=True)
class _ListLevel:
    """One active recovered list level."""

    indent: int
    list_node: List
    last_item: ListItem


def recover_lists(
    elements: list[Element],
    *,
    parent: Document | Heading | Element | None,
) -> list[Element]:
    """Recover nested semantic lists from flat ``list_item`` elements."""
    recovered: list[Element] = []
    list_stack: list[_ListLevel] = []
    pending_blank_lines = 0

    for element in elements:
        if isinstance(element, ListItem):
            pending_blank_lines = 0
            _attach_list_item(element, recovered, list_stack, parent=parent)
            continue

        if element.node_type == "blank_line":
            pending_blank_lines += 1
            recovered.append(element)
            continue

        if _attach_as_item_body(
            element,
            list_stack,
            pending_blank_lines=pending_blank_lines,
        ):
            pending_blank_lines = 0
            continue

        pending_blank_lines = 0
        if list_stack:
            element_indent = _element_indent(element)
            while list_stack and element_indent <= list_stack[-1].indent:
                list_stack.pop()
            if not list_stack:
                list_stack.clear()
        recovered.append(element)

    return recovered


def _attach_list_item(
    item: ListItem,
    recovered: list[Element],
    list_stack: list[_ListLevel],
    *,
    parent: Document | Heading | Element | None,
) -> None:
    """Attach one list item either as sibling or nested child."""
    indent = _indent_width(item.indent)

    while list_stack and indent < list_stack[-1].indent:
        list_stack.pop()

    if not list_stack:
        top_list = List(items=[item], parent=parent)
        recovered.append(top_list)
        list_stack.append(_ListLevel(indent=indent, list_node=top_list, last_item=item))
        return

    current = list_stack[-1]
    if indent == current.indent:
        current.list_node.append_item(item, mark_dirty=False)
        current.last_item = item
        return

    if indent > current.indent:
        nested_list = List(items=[item], parent=current.last_item)
        current.last_item.append_body(nested_list, mark_dirty=False)
        list_stack.append(
            _ListLevel(indent=indent, list_node=nested_list, last_item=item)
        )
        return

    fallback_list = List(items=[item], parent=parent)
    recovered.append(fallback_list)
    list_stack.append(
        _ListLevel(indent=indent, list_node=fallback_list, last_item=item)
    )


def _attach_as_item_body(
    element: Element,
    list_stack: list[_ListLevel],
    *,
    pending_blank_lines: int,
) -> bool:
    """Return whether *element* is attached as body to current list item."""
    if not list_stack:
        return False

    current = list_stack[-1]
    item_indent = _indent_width(current.last_item.indent)
    element_indent = _element_indent(element)
    if element_indent <= item_indent:
        return False

    if pending_blank_lines >= 2 and element_indent <= item_indent:
        return False

    if isinstance(element, Paragraph):
        min_indent = compute_min_indent(element)
        if min_indent is None or min_indent <= item_indent:
            return False

    current.last_item.append_body(element, mark_dirty=False)
    return True


def compute_min_indent(paragraph: Paragraph) -> int | None:
    """Compute minimum indent across non-empty paragraph lines."""
    lines = paragraph.source_text.splitlines()
    indents = [_leading_indent_width(line) for line in lines if line.strip() != ""]
    if not indents:
        return None
    return min(indents)


def _element_indent(element: Element) -> int:
    """Return the first non-empty line indentation width for one element."""
    for line in element.source_text.splitlines():
        if line.strip() == "":
            continue
        return _leading_indent_width(line)
    return 0


def _indent_width(indent: str | None) -> int:
    """Return indentation width for one optional indent string."""
    if indent is None:
        return 0
    return _leading_indent_width(indent)


def _leading_indent_width(value: str) -> int:
    """Return display width for the leading whitespace of one line."""
    width = 0
    for char in value:
        if char == " ":
            width += 1
            continue
        if char == "\t":
            width += 1
            continue
        break
    return width
