"""Shared body-extraction helpers.

Used mostly by [org_parser.document.Document][] and [org_parser.document.Heading][].
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import is_error_node, node_source
from org_parser._nodes import INDENT
from org_parser.element import Logbook, Properties, Repeat
from org_parser.element._dispatch import body_element_factories
from org_parser.element._element import Element, element_from_error_or_unknown
from org_parser.element._structure import Indent

if TYPE_CHECKING:
    from collections.abc import Callable

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading
    from org_parser.text._rich_text import RichText
    from org_parser.time import Clock

# NOTE: Callable is kept in TYPE_CHECKING for the dispatch dict type annotations.

__all__ = [
    "extract_body_element",
    "extract_indent",
    "merge_logbook_drawers",
    "merge_properties_drawers",
]


def merge_properties_drawers(
    drawers: list[Properties],
    *,
    parent: Heading | Document,
) -> Properties | None:
    """Merge repeated properties drawers into one object.

    Args:
        drawers: All collected [org_parser.element.Properties][] drawers in source order.
        parent: Owner object to assign to the merged drawer.

    Returns:
        A single merged [org_parser.element.Properties][], or ``None`` when *drawers* is
        empty. Later drawers override earlier entries for the same key.
    """
    if not drawers:
        return None
    merged_values: dict[str, RichText] = {}
    for drawer in drawers:
        for key, value in drawer.items():
            if key in merged_values:
                del merged_values[key]
            merged_values[key] = value
    return Properties(properties=merged_values, parent=parent)


def merge_logbook_drawers(
    drawers: list[Logbook],
    *,
    parent: Heading | Document,
) -> Logbook | None:
    """Merge repeated logbook drawers into one object.

    Args:
        drawers: All collected [org_parser.element.Logbook][] drawers in source order.
        parent: Owner object to assign to the merged drawer.

    Returns:
        A single merged [org_parser.element.Logbook][], or ``None`` when *drawers* is empty.
    """
    if not drawers:
        return None
    merged_body: list[Element] = []
    merged_clocks: list[Clock] = []
    merged_repeats: list[Repeat] = []
    for drawer in drawers:
        merged_body.extend(drawer.body)
        merged_clocks.extend(drawer.clock_entries)
        merged_repeats.extend(drawer.repeats)
    return Logbook(
        body=merged_body,
        clock_entries=merged_clocks,
        repeats=merged_repeats,
        parent=parent,
    )


def extract_body_element(
    node: tree_sitter.Node,
    *,
    parent: Heading | Document,
    document: Document,
) -> Element:
    """Build one body element instance from a tree-sitter node.

    Error nodes (``ERROR`` type or ``is_missing``) are recovered immediately
    before dispatch so that callers do not need to guard the call site.

    Args:
        node: A tree-sitter child node from a section or zeroth-section.
        parent: Owner heading or document.
        document: The owning [org_parser.document.Document][].

    Returns:
        A semantic [org_parser.element.Element][] subclass matching *node.type*, or a
        recovered [org_parser.element.Paragraph][] for
        error and unrecognised nodes.
    """
    if is_error_node(node):
        return element_from_error_or_unknown(node, document, parent=parent)
    dispatch: dict[str, Callable[..., Element]] = {
        **body_element_factories(),
        INDENT: extract_indent,
    }
    factory = dispatch.get(node.type)
    if factory is None:
        return element_from_error_or_unknown(node, document, parent=parent)
    return factory(node, document, parent=parent)


def extract_indent(
    node: tree_sitter.Node,
    document: Document,
    *,
    parent: Heading | Document,
) -> Indent:
    """Build one [org_parser.element.Indent][] with recursively parsed body nodes.

    Args:
        node: A tree-sitter ``indent`` node.
        document: The owning [org_parser.document.Document][].
        parent: Owner heading or document.

    Returns:
        An [org_parser.element.Indent][] whose body elements are recursively parsed.
    """
    indent_node = node.child_by_field_name("indent")
    indent_text = node_source(indent_node, document)
    indent = indent_text if indent_text != "" else None
    block = Indent(
        body=[
            extract_body_element(child, parent=parent, document=document)
            for child in node.children_by_field_name("body")
            if child.is_named
        ],
        indent=indent,
        parent=parent,
    )
    block.attach_source(node, document)
    return block
