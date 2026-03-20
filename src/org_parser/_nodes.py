"""Tree-sitter grammar node-type name constants for the Org Mode grammar.

All string constants here correspond to ``node.type`` values produced by the
compiled Org Mode tree-sitter grammar.  Centralising them here prevents the
same literal from being scattered across every module that dispatches on node
types.

Constants are grouped by semantic domain and kept in alphabetical order within
each group.
"""

from __future__ import annotations

__all__ = [
    "ANGLE_LINK",
    "AUTHOR",
    "BLANK_LINE",
    "BLOCK",
    "BOLD",
    "CAPTION_KEYWORD",
    "CATEGORY",
    "CENTER_BLOCK",
    "CITATION",
    "CLOCK",
    "CLOSED",
    "CODE",
    "COMMENT",
    "COMMENT_BLOCK",
    "COMPLETION_COUNTER",
    "DEADLINE",
    "DESCRIPTION",
    "DRAWER",
    "DYNAMIC_BLOCK",
    "EXAMPLE_BLOCK",
    "EXPORT_BLOCK",
    "EXPORT_SNIPPET",
    "FIXED_WIDTH",
    "FOOTNOTE_REFERENCE",
    "HEADING",
    "HORIZONTAL_RULE",
    "INLINE_HEADERS",
    "INLINE_SOURCE_BLOCK",
    "ITALIC",
    "LINE_BREAK",
    "LIST_ITEM",
    "LOGBOOK_DRAWER",
    "NODE_PROPERTY",
    "ORG_TABLE",
    "PARAGRAPH",
    "PLAIN_LINK",
    "PLAIN_TEXT",
    "PLANNING",
    "PLANNING_KEYWORD",
    "PLOT_KEYWORD",
    "PROPERTY_DRAWER",
    "QUOTE_BLOCK",
    "RADIO_TARGET",
    "REGULAR_LINK",
    "RESULTS_KEYWORD",
    "SCHEDULED",
    "SPECIAL_BLOCK",
    "SPECIAL_KEYWORD",
    "SRC_BLOCK",
    "STRIKE_THROUGH",
    "TABLEEL_TABLE",
    "TABLE_CELL",
    "TABLE_ROW",
    "TABLE_RULE",
    "TAG",
    "TARGET",
    "TBLFM_LINE",
    "TBLNAME_KEYWORD",
    "TIMESTAMP",
    "TITLE",
    "TODO",
    "TS_DAY",
    "TS_DAYNAME",
    "TS_MONTH",
    "TS_TIME",
    "TS_YEAR",
    "UNDERLINE",
    "VERBATIM",
    "VERSE_BLOCK",
    "ZEROTH_SECTION",
]

# ---------------------------------------------------------------------------
# Document / section structure
# ---------------------------------------------------------------------------

HEADING = "heading"
ZEROTH_SECTION = "zeroth_section"

# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------

PLANNING = "planning"
PLANNING_KEYWORD = "planning_keyword"
TIMESTAMP = "timestamp"

# Planning keyword values — the text content of ``planning_keyword`` nodes
# (e.g. the word ``SCHEDULED`` in the source), not grammar node types.
SCHEDULED = "SCHEDULED"
DEADLINE = "DEADLINE"
CLOSED = "CLOSED"

# ---------------------------------------------------------------------------
# Timestamp sub-nodes
# ---------------------------------------------------------------------------

TS_DAY = "ts_day"
TS_DAYNAME = "ts_dayname"
TS_MONTH = "ts_month"
TS_TIME = "ts_time"
TS_YEAR = "ts_year"

# ---------------------------------------------------------------------------
# Heading components
# ---------------------------------------------------------------------------

COMPLETION_COUNTER = "completion_counter"
TAG = "tag"

# ---------------------------------------------------------------------------
# Keywords
# ---------------------------------------------------------------------------

SPECIAL_KEYWORD = "special_keyword"

# Special keyword values — the upper-cased key text of ``special_keyword``
# nodes (e.g. the word ``TITLE`` in ``#+TITLE:``), not grammar node types.
TITLE = "TITLE"
AUTHOR = "AUTHOR"
CATEGORY = "CATEGORY"
DESCRIPTION = "DESCRIPTION"
TODO = "TODO"

# ---------------------------------------------------------------------------
# Drawers
# ---------------------------------------------------------------------------

DRAWER = "drawer"
LOGBOOK_DRAWER = "logbook_drawer"
NODE_PROPERTY = "node_property"
PROPERTY_DRAWER = "property_drawer"

# ---------------------------------------------------------------------------
# Element types
# ---------------------------------------------------------------------------

BLANK_LINE = "blank_line"
BLOCK = "block"
CAPTION_KEYWORD = "caption_keyword"
CENTER_BLOCK = "center_block"
CLOCK = "clock"
COMMENT = "comment"
COMMENT_BLOCK = "comment_block"
DYNAMIC_BLOCK = "dynamic_block"
EXAMPLE_BLOCK = "example_block"
EXPORT_BLOCK = "export_block"
FIXED_WIDTH = "fixed_width"
HORIZONTAL_RULE = "horizontal_rule"
LIST_ITEM = "list_item"
ORG_TABLE = "org_table"
PARAGRAPH = "paragraph"
PLOT_KEYWORD = "plot_keyword"
QUOTE_BLOCK = "quote_block"
RESULTS_KEYWORD = "results_keyword"
SPECIAL_BLOCK = "special_block"
SRC_BLOCK = "src_block"
TABLEEL_TABLE = "tableel_table"
TBLNAME_KEYWORD = "tblname_keyword"
VERSE_BLOCK = "verse_block"

# ---------------------------------------------------------------------------
# Table sub-nodes
# ---------------------------------------------------------------------------

TABLE_CELL = "table_cell"
TABLE_ROW = "table_row"
TABLE_RULE = "table_rule"
TBLFM_LINE = "tblfm_line"

# ---------------------------------------------------------------------------
# Inline object types
# ---------------------------------------------------------------------------

ANGLE_LINK = "angle_link"
BOLD = "bold"
CITATION = "citation"
CODE = "code"
EXPORT_SNIPPET = "export_snippet"
FOOTNOTE_REFERENCE = "footnote_reference"
INLINE_HEADERS = "inline_headers"
INLINE_SOURCE_BLOCK = "inline_source_block"
ITALIC = "italic"
LINE_BREAK = "line_break"
PLAIN_LINK = "plain_link"
PLAIN_TEXT = "plain_text"
RADIO_TARGET = "radio_target"
REGULAR_LINK = "regular_link"
STRIKE_THROUGH = "strike_through"
TARGET = "target"
UNDERLINE = "underline"
VERBATIM = "verbatim"
