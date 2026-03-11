"""org_parser — Python bindings for the tree-sitter org-mode parser.

This package provides convenience helpers for loading and dumping Org Mode
documents as :class:`org_parser.document.Document` instances.
"""

from __future__ import annotations

from pathlib import Path

from org_parser._lang import PARSER
from org_parser.document import Document

__all__ = ["Document", "dump", "dumps", "load", "loads"]


def load(filename: str) -> Document:
    """Load an Org Mode document from a file.

    Args:
        filename: Path to the Org Mode file.

    Returns:
        Parsed :class:`~org_parser.document.Document` instance.
    """
    path = Path(filename)
    source = path.read_bytes()
    tree = PARSER.parse(source)
    return Document.from_tree(tree, filename, source)


def loads(input: str, filename: str | None = None) -> Document:
    """Load an Org Mode document from a string.

    Args:
        input: Org Mode text to parse.
        filename: Optional filename to assign to the parsed document.

    Returns:
        Parsed :class:`~org_parser.document.Document` instance.
    """
    assigned_filename = filename if filename is not None else ""
    source = input.encode()
    tree = PARSER.parse(source)
    return Document.from_tree(tree, assigned_filename, source)


def dumps(document: Document) -> str:
    """Return Org Mode text for a parsed document.

    Args:
        document: Parsed document instance.

    Returns:
        Verbatim Org Mode source text.
    """
    return document.source.decode()


def dump(document: Document, filename: str | None = None) -> None:
    """Write a parsed document to disk.

    The output path is *filename* when provided; otherwise
    :attr:`document.filename <org_parser.document.Document.filename>`.

    Args:
        document: Parsed document instance.
        filename: Optional output path.

    Raises:
        ValueError: If neither *filename* nor ``document.filename`` is set.
    """
    target = filename if filename is not None else document.filename
    if target == "":
        raise ValueError("No output filename provided")
    Path(target).write_text(dumps(document))
