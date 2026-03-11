"""Document-level parsing, semantic classes, and raw tree access.

This subpackage provides:

* :class:`Document` — the top-level semantic representation of an Org file,
  including keyword properties (``TITLE``, ``AUTHOR``, …), the zeroth-section
  body, and top-level headings.
* :class:`Heading` — a heading / sub-heading with its parsed components
  (level, TODO state, priority, title, tags, body, sub-headings).
* :func:`load_raw` — low-level helper that parses an ``.org`` file and
  returns the unprocessed :class:`~tree_sitter.Tree`.

Example::

    from org_parser.document import Document, load_raw

    tree = load_raw("my-notes.org")
    source = open("my-notes.org", "rb").read()
    doc = Document.from_tree(tree, "my-notes.org", source)
    print(doc.title)
"""

from org_parser.document._document import Document
from org_parser.document._heading import Heading
from org_parser.document._loader import load_raw

__all__ = ["Document", "Heading", "load_raw"]
