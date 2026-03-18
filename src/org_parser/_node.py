"""Shared tree-sitter node text utilities.

These helpers centralise the two recurrent patterns for extracting decoded
source text from a tree-sitter node:

* :func:`node_text` — when you already hold the raw ``bytes`` source buffer
  (e.g. inside ``from_node`` factory methods).
* :func:`node_source` — when you hold a
  :class:`~org_parser.document._document.Document` reference and need to
  reach back into it (e.g. inside ``__str__`` methods on element objects).

Both functions return an empty string rather than raising when the node or
document argument is ``None``, so callers do not need separate guard clauses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document

__all__ = ["node_source", "node_text"]


def node_text(node: tree_sitter.Node | None, source: bytes) -> str:
    """Return the decoded text covered by *node* in *source*.

    Args:
        node: A tree-sitter node, or ``None``.
        source: The raw source bytes buffer the node was parsed from.

    Returns:
        The decoded substring ``source[node.start_byte:node.end_byte]``,
        or an empty string when *node* is ``None``.
    """
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode()


def node_source(node: tree_sitter.Node | None, document: Document | None) -> str:
    """Return the decoded source text of *node* within *document*.

    Args:
        node: A tree-sitter node, or ``None`` for programmatically constructed
            elements that carry no parse-tree backing.
        document: The owning :class:`~org_parser.document._document.Document`,
            or ``None``.

    Returns:
        The decoded source slice, or an empty string when either argument is
        ``None``.
    """
    if node is None or document is None:
        return ""
    return document.source[node.start_byte : node.end_byte].decode()
