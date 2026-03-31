"""Document-level parsing, semantic classes, and raw tree access.

This subpackage provides:

* [org_parser.document.Document][] — the top-level semantic representation of an Org file,
  including keyword properties (``TITLE``, ``AUTHOR``, …), the zeroth-section
  body, and top-level headings.
* [org_parser.document.Heading][] — a heading / sub-heading with its parsed components
  (level, TODO state, priority, title, tags, body, sub-headings).
"""

from org_parser.document._document import Document, ParseError
from org_parser.document._heading import Heading
from org_parser.document._loader import load_raw

__all__ = ["Document", "Heading", "ParseError", "load_raw"]
