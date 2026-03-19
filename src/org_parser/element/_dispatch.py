"""Shared body-element dispatch table for section and nested contexts.

:func:`body_element_factories` returns the canonical mapping from
tree-sitter node type strings to ``from_node`` factory callables.  The
result is cached after the first call so the dict is only built once per
interpreter session.

All three dispatch sites — :func:`~org_parser.document._body.extract_body_element`,
:func:`~org_parser.element._block._extract_nested_element`, and
:func:`~org_parser.element._drawer._extract_drawer_body_element` — import
this function and extend it with their context-specific entries.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from org_parser._nodes import (
    BLANK_LINE,
    CAPTION_KEYWORD,
    CENTER_BLOCK,
    CLOCK,
    COMMENT,
    COMMENT_BLOCK,
    DRAWER,
    DYNAMIC_BLOCK,
    EXAMPLE_BLOCK,
    EXPORT_BLOCK,
    FIXED_WIDTH,
    HORIZONTAL_RULE,
    LIST_ITEM,
    LOGBOOK_DRAWER,
    ORG_TABLE,
    PARAGRAPH,
    PLOT_KEYWORD,
    PROPERTY_DRAWER,
    QUOTE_BLOCK,
    RESULTS_KEYWORD,
    SPECIAL_BLOCK,
    SRC_BLOCK,
    TABLEEL_TABLE,
    TBLNAME_KEYWORD,
    VERSE_BLOCK,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from org_parser.element._element import Element

__all__ = ["body_element_factories"]


@lru_cache(maxsize=1)
def body_element_factories() -> dict[str, Callable[..., Element]]:
    """Return the shared body-element factory dispatch table.

    The mapping covers every named node type that can appear as a direct
    child of a ``section`` or ``zeroth_section`` body — except for the
    ``block`` (indentation-wrapper) and ``special_keyword`` nodes, which
    are context-specific and handled by each call site.

    The dict is built with lazy imports on the first call and then cached,
    so the cost is incurred only once per interpreter session.

    Returns:
        A ``dict`` mapping tree-sitter node type strings to two-argument
        ``from_node(node, document, *, parent=None)`` callables.
    """
    # Lazy imports avoid circular dependencies at module level.
    # (_block imports _drawer lazily; _drawer imports _block at module level;
    #  _dispatch is imported by all three at module level, so it must not
    #  import any of them at module level itself.)
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
    from org_parser.element._drawer import Drawer, Logbook, Properties
    from org_parser.element._keyword import (
        CaptionKeyword,
        PlotKeyword,
        ResultsKeyword,
        TblnameKeyword,
    )
    from org_parser.element._list import ListItem
    from org_parser.element._paragraph import Paragraph
    from org_parser.element._structure import BlankLine, Comment, HorizontalRule
    from org_parser.element._table import Table
    from org_parser.time import Clock

    return {
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
        BLANK_LINE: BlankLine.from_node,
        CAPTION_KEYWORD: CaptionKeyword.from_node,
        COMMENT: Comment.from_node,
        HORIZONTAL_RULE: HorizontalRule.from_node,
        PLOT_KEYWORD: PlotKeyword.from_node,
        RESULTS_KEYWORD: ResultsKeyword.from_node,
        TBLNAME_KEYWORD: TblnameKeyword.from_node,
    }
