"""Implementation of :func:`load_raw` — raw org-file parsing."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from org_parser._lang import PARSER

if TYPE_CHECKING:
    import tree_sitter

__all__ = ["load_raw"]


def load_raw(path: str | Path) -> tree_sitter.Tree:
    """Parse an org file and return the raw tree-sitter parse tree.

    The returned [tree_sitter.Tree][] gives full access to the parse
    tree via its [tree_sitter.Tree.root_node][] attribute. No
    post-processing or error checking is performed — callers receive exactly
    what the tree-sitter parser produces, including any ``ERROR`` nodes for
    content that could not be matched by the grammar.

    Args:
        path: Absolute or relative path to the ``.org`` file to parse.

    Returns:
        A [tree_sitter.Tree][] whose root node has type ``"document"``.

    Raises:
        FileNotFoundError: If *path* does not exist on the filesystem.
        OSError: If the file exists but cannot be read (permission error,
            device error, etc.).
    """
    resolved = Path(path)
    if not resolved.exists():
        raise FileNotFoundError(f"No such file or directory: {str(resolved)!r}")

    source = resolved.read_bytes()
    return PARSER.parse(source)
