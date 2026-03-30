"""Shared tree-sitter node utilities.

These helpers centralise recurring patterns for inspecting and extracting
decoded source text from tree-sitter nodes:

* :func:`is_error_node` — classify a node as an error or missing token.
* :func:`node_text` — when you already hold the raw ``bytes`` source buffer
  (e.g. inside ``from_node`` factory methods).
* :func:`node_source` — when you hold a
  :class:`~org_parser.document._document.Document` reference and need to
  reach back into it (e.g. inside ``__str__`` methods on element objects).

Both text functions return an empty string rather than raising when the node
or document argument is ``None``, so callers do not need separate guard
clauses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document

__all__ = ["is_error_node", "node_source", "report_internal_parse_errors"]

_ERROR_NODE_TYPE = "ERROR"


def is_error_node(node: tree_sitter.Node) -> bool:
    """Return *True* if *node* is a parse-error or missing token.

    Args:
        node: Any tree-sitter node to inspect.

    Returns:
        ``True`` for ``ERROR``-typed nodes and for nodes where
        ``node.is_missing`` is set by the parser's error-recovery.
    """
    return node.type == _ERROR_NODE_TYPE or node.is_missing


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

    Raises:
        ValueError: If the provided document has no backing source bytes.
    """
    if node is None or document is None:
        return ""
    return document.source_for(node).decode()


def report_internal_parse_errors(node: tree_sitter.Node, document: Document) -> None:
    """Report top-level parse-error descendants inside *node*.

    This records ``ERROR`` and missing nodes nested within a semantic object's
    parse subtree so object-internal parse issues propagate to
    :attr:`Document.errors`. Only top-level error regions are reported to avoid
    duplicate nested entries for the same malformed segment.
    """
    stack: list[tuple[tree_sitter.Node, bool]] = [(node, False)]
    while stack:
        current, has_error_ancestor = stack.pop()
        current_is_error = is_error_node(current)
        if current_is_error and not has_error_ancestor:
            document.report_error(current)
        child_has_error_ancestor = has_error_ancestor or current_is_error
        stack.extend((child, child_has_error_ancestor) for child in reversed(current.children))
