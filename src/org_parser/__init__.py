"""org_parser — Python bindings for the tree-sitter org-mode parser.

This package provides convenience helpers for loading and dumping Org Mode
documents as [org_parser.document.Document][] instances.
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
        Parsed [org_parser.document.Document][] instance.

    Example:
    ```python
    >>> from org_parser import load
    >>> document = load('path/to/file.org')
    >>> document.children[0].title_text
    'Some heading'
    ```
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
        Parsed [org_parser.document.Document][] instance.

    Example:
    ```python
    >>> from org_parser import loads
    >>> document = loads("* TODO Heading 1")
    >>> document.children[0].todo
    'TODO'
    ```
    """
    assigned_filename = filename if filename is not None else ""
    source = input.encode()
    tree = PARSER.parse(source)
    return Document.from_tree(tree, assigned_filename, source)


def dumps(document: Document) -> str:
    """Return Org Mode text for a parsed document.

    Produces the complete document text including all headings.  For clean
    (unmodified) parse-backed documents the original source is returned
    verbatim; for dirty documents every section is reconstructed from its
    semantic fields.

    Args:
        document: Parsed document instance.

    Returns:
        Full Org Mode source text.

    Example:
    ```python
    >>> from org_parser import dumps, loads
    >>> document = loads("* TODO Heading 1")
    >>> dumps(document).startswith("* TODO")
    True
    ```
    """
    return document.render()


def dump(document: Document, filename: str | None = None) -> None:
    """Write a parsed document to disk.

    The output path is *filename* when provided; otherwise
    [document.filename][org_parser.document.Document.filename].

    Args:
        document: Parsed document instance.
        filename: Optional output path.

    Raises:
        ValueError: If neither *filename* nor ``document.filename`` is set.

    Example:
    ```python
    >>> from pathlib import Path
    >>> from org_parser import dump, loads
    >>> document = loads("* TODO Heading 1")
    >>> dump(document, 'path/to/file.org')
    >>> out = Path('path/to/file.org')
    >>> out.read_text().startswith("* TODO")
    True
    ```
    """
    target = filename if filename is not None else document.filename
    if target == "":
        raise ValueError("No output filename provided")
    Path(target).write_text(dumps(document))
