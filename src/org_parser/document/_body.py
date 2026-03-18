"""Shared body-extraction helpers for :class:`Document` and :class:`Heading`.

These functions are factored out to avoid duplication between
:mod:`org_parser.document._document` and :mod:`org_parser.document._heading`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._nodes import (
    BLOCK,
    CENTER_BLOCK,
    CLOCK,
    COMMENT_BLOCK,
    DRAWER,
    DYNAMIC_BLOCK,
    EXAMPLE_BLOCK,
    EXPORT_BLOCK,
    FIXED_WIDTH,
    LIST_ITEM,
    LOGBOOK_DRAWER,
    ORG_TABLE,
    PARAGRAPH,
    PROPERTY_DRAWER,
    QUOTE_BLOCK,
    SPECIAL_BLOCK,
    SRC_BLOCK,
    TABLEEL_TABLE,
    VERSE_BLOCK,
)
from org_parser.element import (
    CenterBlock,
    CommentBlock,
    Drawer,
    DynamicBlock,
    ExampleBlock,
    ExportBlock,
    FixedWidthBlock,
    ListItem,
    Logbook,
    Properties,
    QuoteBlock,
    Repeat,
    SourceBlock,
    SpecialBlock,
    VerseBlock,
)
from org_parser.element._element import Element, element_from_error_or_unknown
from org_parser.element._indent_block import IndentBlock
from org_parser.element._paragraph import Paragraph
from org_parser.element._table import Table
from org_parser.time import Clock

if TYPE_CHECKING:
    from collections.abc import Callable

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading
    from org_parser.text._rich_text import RichText

# NOTE: Callable is kept in TYPE_CHECKING for the dispatch dict type annotations.

__all__ = [
    "extract_body_element",
    "extract_indent_block",
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
        drawers: All collected :class:`Properties` drawers in source order.
        parent: Owner object to assign to the merged drawer.

    Returns:
        A single merged :class:`Properties`, or ``None`` when *drawers* is
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
        drawers: All collected :class:`Logbook` drawers in source order.
        parent: Owner object to assign to the merged drawer.

    Returns:
        A single merged :class:`Logbook`, or ``None`` when *drawers* is empty.
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
    document: Document | None = None,
) -> Element:
    """Build one body element instance from a tree-sitter node.

    Args:
        node: A tree-sitter child node from a section or zeroth-section.
        parent: Owner heading or document.
        document: The owning :class:`Document`, or *None*. When *None*,
            source defaults to ``b""`` and errors are not recorded.

    Returns:
        A semantic :class:`Element` subclass matching *node.type*, or a
        recovered :class:`~org_parser.element._paragraph.Paragraph` for
        error nodes.
    """
    dispatch: dict[str, Callable[..., Element]] = {
        PARAGRAPH: Paragraph.from_node,
        ORG_TABLE: Table.from_node,
        TABLEEL_TABLE: Table.from_node,
        CLOCK: Clock.from_node,
        DRAWER: Drawer.from_node,
        LOGBOOK_DRAWER: Logbook.from_node,
        PROPERTY_DRAWER: Properties.from_node,
        CENTER_BLOCK: CenterBlock.from_node,
        QUOTE_BLOCK: QuoteBlock.from_node,
        SPECIAL_BLOCK: SpecialBlock.from_node,
        DYNAMIC_BLOCK: DynamicBlock.from_node,
        COMMENT_BLOCK: CommentBlock.from_node,
        EXAMPLE_BLOCK: ExampleBlock.from_node,
        EXPORT_BLOCK: ExportBlock.from_node,
        SRC_BLOCK: SourceBlock.from_node,
        VERSE_BLOCK: VerseBlock.from_node,
        FIXED_WIDTH: FixedWidthBlock.from_node,
        LIST_ITEM: ListItem.from_node,
        BLOCK: extract_indent_block,
    }
    factory = dispatch.get(node.type)
    if factory is None:
        return element_from_error_or_unknown(node, document, parent=parent)
    return factory(node, document, parent=parent)


def extract_indent_block(
    node: tree_sitter.Node,
    document: Document | None = None,
    *,
    parent: Heading | Document,
) -> IndentBlock:
    """Build one :class:`IndentBlock` with recursively parsed body nodes.

    Args:
        node: A tree-sitter ``block`` node.
        document: The owning :class:`Document`, or *None*.
        parent: Owner heading or document.

    Returns:
        An :class:`IndentBlock` whose body elements are recursively parsed.
    """
    block = IndentBlock(
        body=[
            extract_body_element(child, parent=parent, document=document)
            for child in node.children_by_field_name("body")
            if child.is_named
        ],
        parent=parent,
    )
    block.attach_backing(node, document)
    return block
