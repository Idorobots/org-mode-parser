"""Keyword element classes for Org special and affiliated keyword lines.

This module covers all ``#+KEY:`` lines that appear in document and section
bodies:

* :class:`Keyword` — generic ``#+KEY: value`` special keyword
  (``special_keyword`` node, e.g. ``#+TITLE:``, ``#+AUTHOR:``).
* :class:`CaptionKeyword` — ``#+CAPTION:`` affiliated keyword.
* :class:`TblnameKeyword` — ``#+TBLNAME:`` affiliated keyword.
* :class:`ResultsKeyword` — ``#+RESULTS:`` affiliated keyword.
* :class:`PlotKeyword` — ``#+PLOT:`` affiliated keyword.

The four affiliated keyword classes share a common base,
:class:`_AffiliatedKeyword`, which handles the ``value`` field that all four
expose.

.. note::
   The ``#+RESULTS[hash]:`` hash annotation is not yet implemented in the
   underlying tree-sitter grammar; ``#+RESULTS[hash]:`` currently parses as
   an ``ERROR`` node.  :class:`ResultsKeyword` therefore exposes only the
   ``value`` field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import node_source
from org_parser.element._element import Element
from org_parser.text._rich_text import RichText

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = [
    "CaptionKeyword",
    "Keyword",
    "PlotKeyword",
    "ResultsKeyword",
    "TblnameKeyword",
]


# ---------------------------------------------------------------------------
# Special keyword (zeroth-section)
# ---------------------------------------------------------------------------


class Keyword(Element):
    """Special keyword element, e.g. ``#+TITLE: Value``.

    Args:
        key: Upper-cased keyword key.
        value: Keyword value rich text.
        parent: Optional parent owner object.
    """

    def __init__(
        self,
        *,
        key: str,
        value: RichText,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._key = key.upper()
        self._value = value
        self._value.parent = self

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Keyword:
        """Create a :class:`Keyword` from a tree-sitter ``special_keyword`` node.

        Args:
            node: The ``special_keyword`` tree-sitter node.
            document: The owning :class:`Document`.
            parent: Optional parent owner object.
        """
        key_node = node.child_by_field_name("key")
        key = document.source_for(key_node).decode().upper() if key_node else ""

        value_node = node.child_by_field_name("value")
        value = (
            RichText.from_node(value_node, document=document)
            if value_node is not None
            else RichText("")
        )

        kw = cls(key=key, value=value, parent=parent)
        kw._node = node
        kw._document = document
        return kw

    @property
    def key(self) -> str:
        """The upper-cased keyword key."""
        return self._key

    @key.setter
    def key(self, value: str) -> None:
        """Set keyword key and mark as dirty."""
        self._key = value.upper()
        self._mark_dirty()

    @property
    def value(self) -> RichText:
        """The mutable keyword value rich text."""
        return self._value

    @value.setter
    def value(self, value: RichText) -> None:
        """Set keyword value and mark as dirty."""
        self._value = value
        self._value.parent = self
        self._mark_dirty()

    def reformat(self) -> None:
        """Mark value and this keyword dirty for scratch-built rendering."""
        self._value.reformat()
        self.mark_dirty()

    def __str__(self) -> str:
        """Render keyword line.

        Clean parse-backed instances preserve their verbatim source text.
        Dirty instances are rendered from semantic fields.
        """
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        rendered_value = str(self._value)
        if rendered_value == "":
            return f"#+{self._key}:\n"
        return f"#+{self._key}: {rendered_value}\n"

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"Keyword(key={self._key!r}, value={self._value!r})"


# ---------------------------------------------------------------------------
# Affiliated keywords — shared base
# ---------------------------------------------------------------------------


class _AffiliatedKeyword(Element):
    """Base class for affiliated keyword lines (``#+KEY: value``).

    Subclasses set :attr:`_keyword` to the canonical upper-cased keyword
    string used for rendering (e.g. ``"CAPTION"``, ``"TBLNAME"``).

    Args:
        value: Optional plain-text value following the keyword.
    """

    _keyword: str = ""  # overridden by each concrete subclass as a class variable

    def __init__(
        self,
        *,
        value: str | None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._value = value

    @classmethod
    def _value_from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
    ) -> str | None:
        """Extract the optional ``value`` field text from an affiliated keyword node."""
        value_node = node.child_by_field_name("value")
        if value_node is None:
            return None
        text = document.source_for(value_node).decode()
        return text if text != "" else None

    @property
    def value(self) -> str | None:
        """Optional plain-text value following the keyword, or ``None``."""
        return self._value

    @value.setter
    def value(self, v: str | None) -> None:
        """Set the keyword value and mark this element as dirty."""
        self._value = v
        self._mark_dirty()

    def __str__(self) -> str:
        """Render the keyword line, preserving source while parse-backed and clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        if self._value:
            return f"#+{self._keyword}: {self._value}\n"
        return f"#+{self._keyword}:\n"

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return f"{self.__class__.__name__}(value={self._value!r})"


# ---------------------------------------------------------------------------
# Concrete affiliated keyword classes
# ---------------------------------------------------------------------------


class CaptionKeyword(_AffiliatedKeyword):
    """A ``#+CAPTION:`` affiliated keyword line.

    Captions annotate the element immediately following them (typically a
    table or image).  The optional *short* form (``#+CAPTION[short]:`` in
    Org syntax) is stored separately.

    Args:
        value: The caption text following ``#+CAPTION:``.
        short: Optional short caption text inside ``[…]``, or ``None``.
    """

    _keyword = "CAPTION"

    def __init__(
        self,
        *,
        value: str | None,
        short: str | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(value=value, parent=parent)
        self._short = short

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> CaptionKeyword:
        """Create a :class:`CaptionKeyword` from a ``caption_keyword`` node."""
        optval_node = node.child_by_field_name("optval")
        if optval_node is None:
            short = None
        else:
            short = document.source_for(optval_node).decode()
        elem = cls(
            value=cls._value_from_node(node, document),
            short=short,
            parent=parent,
        )
        elem.attach_source(node, document)
        return elem

    @property
    def short(self) -> str | None:
        """Optional short caption text (the ``[…]`` portion), or ``None``."""
        return self._short

    @short.setter
    def short(self, value: str | None) -> None:
        """Set the short caption and mark this element as dirty."""
        self._short = value
        self._mark_dirty()

    def __str__(self) -> str:
        """Render the caption line, preserving source while parse-backed and clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        short_part = f"[{self._short}]" if self._short is not None else ""
        if self._value:
            return f"#+CAPTION{short_part}: {self._value}\n"
        return f"#+CAPTION{short_part}:\n"

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        cls_name = self.__class__.__name__
        if self._short is not None:
            return f"{cls_name}(value={self._value!r}, short={self._short!r})"
        return f"{cls_name}(value={self._value!r})"


class TblnameKeyword(_AffiliatedKeyword):
    """A ``#+TBLNAME:`` affiliated keyword line.

    Assigns a name to the table immediately following it, allowing other
    parts of the document to refer to it by name.

    Args:
        value: The table name, or ``None`` when the keyword has no value.
    """

    _keyword = "TBLNAME"

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> TblnameKeyword:
        """Create a :class:`TblnameKeyword` from a ``tblname_keyword`` node."""
        elem = cls(value=cls._value_from_node(node, document), parent=parent)
        elem.attach_source(node, document)
        return elem


class ResultsKeyword(_AffiliatedKeyword):
    """A ``#+RESULTS:`` affiliated keyword line.

    Marks the block immediately following it as the results of a source
    block evaluation.

    Args:
        value: Optional trailing text on the results line, or ``None``.

    .. note::
       The ``#+RESULTS[hash]:`` hash annotation defined in the Org Mode
       specification is not yet implemented in the underlying tree-sitter
       grammar.  Inputs containing ``[hash]`` currently produce an
       ``ERROR`` parse node; the hash therefore cannot be exposed here
       until grammar support is added.
    """

    _keyword = "RESULTS"

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> ResultsKeyword:
        """Create a :class:`ResultsKeyword` from a ``results_keyword`` node."""
        elem = cls(value=cls._value_from_node(node, document), parent=parent)
        elem.attach_source(node, document)
        return elem


class PlotKeyword(_AffiliatedKeyword):
    """A ``#+PLOT:`` affiliated keyword line.

    Carries gnuplot configuration for the table immediately following it.

    Args:
        value: The plot configuration string, or ``None``.
    """

    _keyword = "PLOT"

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> PlotKeyword:
        """Create a :class:`PlotKeyword` from a ``plot_keyword`` node."""
        elem = cls(value=cls._value_from_node(node, document), parent=parent)
        elem.attach_source(node, document)
        return elem
