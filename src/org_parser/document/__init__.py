"""Document-level parsing and raw tree access.

The primary public API of this subpackage is :func:`load_raw`, which parses
an ``.org`` file and returns the unprocessed :class:`~tree_sitter.Tree` from
the tree-sitter parser.

Example::

    from org_parser.document import load_raw

    tree = load_raw("my-notes.org")
    print(tree.root_node.type)  # "document"
"""

from org_parser.document._loader import load_raw

__all__ = ["load_raw"]
