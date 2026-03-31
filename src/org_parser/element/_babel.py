"""Babel call element class for Org ``#+call:`` lines.

This module provides [org_parser.element.BabelCall][], the Python wrapper for the
``babel_call`` tree-sitter node produced by the Org grammar.  A babel call
line invokes a named source block by name, optionally supplying a header
argument list and an argument expression:

    #+call: NAME[INSIDE-HEADER](ARGUMENTS)[OUTSIDE-HEADER]

All four components except the name are optional.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import node_source
from org_parser.element._element import Element

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["BabelCall"]


class BabelCall(Element):
    """A ``#+call:`` babel call element.

    Represents a top-level Org babel call line of the form::

        # +call: NAME[INSIDE-HEADER](ARGUMENTS)[OUTSIDE-HEADER]

    Only *name* is required; the three optional components default to
    ``None`` when absent from the source.

    Args:
        name: The called function name (e.g. ``"double"``).
        arguments: Optional argument string inside ``(…)``.
        inside_header: Optional header string inside the first ``[…]``.
        outside_header: Optional header string inside the second ``[…]``.
        parent: Optional parent owner object.

    Example:
    ```python
    >>> from org_parser.element import BabelCall
    >>> c = BabelCall.from_source("#+call: foo(bar)")
    >>> c.name
    'foo'
    >>> c.arguments
    'bar'
    ```
    """

    def __init__(
        self,
        *,
        name: str,
        arguments: str | None = None,
        inside_header: str | None = None,
        outside_header: str | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._name = name
        self._arguments = arguments
        self._inside_header = inside_header
        self._outside_header = outside_header

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> BabelCall:
        """Create a [org_parser.element.BabelCall][] from a ``babel_call`` tree-sitter node.

        Args:
            node: The ``babel_call`` tree-sitter node.
            document: The owning [org_parser.document.Document][].
            parent: Optional parent owner object.
        """
        name_node = node.child_by_field_name("name")
        args_node = node.child_by_field_name("arguments")
        inside_node = node.child_by_field_name("inside_header")
        outside_node = node.child_by_field_name("outside_header")

        elem = cls(
            name=node_source(name_node, document) if name_node else "",
            arguments=node_source(args_node, document) if args_node else None,
            inside_header=node_source(inside_node, document) if inside_node else None,
            outside_header=node_source(outside_node, document) if outside_node else None,
            parent=parent,
        )
        elem.attach_source(node, document)
        return elem

    # -- properties ----------------------------------------------------------

    @property
    def name(self) -> str:
        """The name of the called function."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set the called function name."""
        self._name = value
        self.mark_dirty()

    @property
    def arguments(self) -> str | None:
        """Optional argument string, or ``None`` when no arguments are given."""
        return self._arguments

    @arguments.setter
    def arguments(self, value: str | None) -> None:
        """Set the argument string."""
        self._arguments = value
        self.mark_dirty()

    @property
    def inside_header(self) -> str | None:
        """Optional inside-header string (the first ``[…]``), or ``None``."""
        return self._inside_header

    @inside_header.setter
    def inside_header(self, value: str | None) -> None:
        """Set the inside-header string."""
        self._inside_header = value
        self.mark_dirty()

    @property
    def outside_header(self) -> str | None:
        """Optional outside-header string (the second ``[…]``), or ``None``."""
        return self._outside_header

    @outside_header.setter
    def outside_header(self, value: str | None) -> None:
        """Set the outside-header string."""
        self._outside_header = value
        self.mark_dirty()

    # -- rendering -----------------------------------------------------------

    def __str__(self) -> str:
        """Render the babel call line.

        Clean parse-backed instances preserve their verbatim source text.
        Dirty or scratch-built instances are reconstructed from fields.
        """
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        inside = f"[{self._inside_header}]" if self._inside_header is not None else ""
        args = self._arguments if self._arguments is not None else ""
        outside = f"[{self._outside_header}]" if self._outside_header is not None else ""
        return f"#+call: {self._name}{inside}({args}){outside}\n"

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        parts = [f"name={self._name!r}"]
        if self._arguments is not None:
            parts.append(f"arguments={self._arguments!r}")
        if self._inside_header is not None:
            parts.append(f"inside_header={self._inside_header!r}")
        if self._outside_header is not None:
            parts.append(f"outside_header={self._outside_header!r}")
        return f"BabelCall({', '.join(parts)})"
