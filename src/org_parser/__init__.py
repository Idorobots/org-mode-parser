"""org_parser — Python bindings for the tree-sitter org-mode parser.

This package provides a thin layer over the compiled tree-sitter grammar for
Emacs Org Mode. The primary entry point for raw parsing is
:func:`org_parser.document.load_raw`.

Subpackages
-----------
document
    Document-level parsing and raw tree access.
element
    Greater and lesser element representations (future).
text
    Rich text / markup object representations (future).
"""

__all__: list[str] = []
