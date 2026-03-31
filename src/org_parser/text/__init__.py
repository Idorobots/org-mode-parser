"""Rich text and inline object representations.

This subpackage exposes [org_parser.text.RichText][] together with public inline object
abstractions used to construct or inspect rich text programmatically.
"""

from org_parser.text._inline import (
    AngleLink,
    Bold,
    Citation,
    Code,
    CompletionCounter,
    ExportSnippet,
    FootnoteReference,
    InlineBabelCall,
    InlineEntity,
    InlineObject,
    InlineSourceBlock,
    Italic,
    LineBreak,
    Macro,
    PlainLink,
    PlainText,
    RadioTarget,
    RegularLink,
    StrikeThrough,
    Subscript,
    Superscript,
    Target,
    Underline,
    Verbatim,
)
from org_parser.text._rich_text import RichText
from org_parser.time import Timestamp

__all__ = [
    "AngleLink",
    "Bold",
    "Citation",
    "Code",
    "CompletionCounter",
    "ExportSnippet",
    "FootnoteReference",
    "InlineBabelCall",
    "InlineEntity",
    "InlineObject",
    "InlineSourceBlock",
    "Italic",
    "LineBreak",
    "Macro",
    "PlainLink",
    "PlainText",
    "RadioTarget",
    "RegularLink",
    "RichText",
    "StrikeThrough",
    "Subscript",
    "Superscript",
    "Target",
    "Timestamp",
    "Underline",
    "Verbatim",
]
