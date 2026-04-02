"""Keyword element classes for Org special and affiliated keyword lines.

This module covers all ``#+KEY:`` lines that appear in document and section
bodies:

* [org_parser.element.Keyword][] — generic ``#+KEY: value`` special keyword
  (``special_keyword`` node, e.g. ``#+TITLE:``, ``#+AUTHOR:``).
* [org_parser.element.CaptionKeyword][] — ``#+CAPTION:`` affiliated keyword.
* [org_parser.element.TblnameKeyword][] — ``#+TBLNAME:`` affiliated keyword.
* [org_parser.element.ResultsKeyword][] — ``#+RESULTS:`` affiliated keyword.
* [org_parser.element.PlotKeyword][] — ``#+PLOT:`` affiliated keyword.

The four affiliated keyword classes share a common base,
[org_parser.element.AffiliatedKeyword][], which handles the ``value`` field that all four
expose.

.. note::
   The ``#+RESULTS[hash]:`` hash annotation is not yet implemented in the
   underlying tree-sitter grammar; ``#+RESULTS[hash]:`` currently parses as
   an ``ERROR`` node.  [org_parser.element.ResultsKeyword][] therefore exposes only the
   ``value`` field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import node_source
from org_parser.element._element import Element
from org_parser.text._rich_text import RichText, coerce_rich_text

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = [
    "AffiliatedKeyword",
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

    Example:
    ```python
    >>> from org_parser import loads
    >>> document.keywords.append(Keyword.from_source("#+TITLE: Document"))
    >>> print(str(document))
    #+TITLE: Document
    ```
    """

    def __init__(
        self,
        *,
        key: str,
        value: RichText | str,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._key = key.upper()
        self._value = coerce_rich_text(value)
        self._value.parent = self

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Keyword:
        """Create a [org_parser.element.Keyword][] from a tree-sitter ``special_keyword`` node.

        Args:
            node: The ``special_keyword`` tree-sitter node.
            document: The owning [org_parser.document.Document][].
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
        """Set keyword key."""
        self._key = value.upper()
        self.mark_dirty()

    @property
    def value(self) -> RichText:
        """The mutable keyword value rich text."""
        return self._value

    @value.setter
    def value(self, value: RichText | str) -> None:
        """Set keyword value."""
        self._value = coerce_rich_text(value)
        self._value.parent = self
        self.mark_dirty()

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


class AffiliatedKeyword(Element):
    """Base class for affiliated keyword lines (``#+KEY: value``).

    Affiliated keywords annotate the element immediately following them in
    the document body.  The four concrete subclasses are
    [org_parser.element.CaptionKeyword][], [org_parser.element.TblnameKeyword][],
    [org_parser.element.ResultsKeyword][], and [org_parser.element.PlotKeyword][].

    Subclasses set `_keyword` to the canonical upper-cased keyword string used for
    rendering (e.g. ``"CAPTION"``, ``"TBLNAME"``).

    Args:
        value: Optional plain-text value following the keyword.

    Example:
    ```python
    >>> from org_parser.element import CaptionKeyword
    >>> document = loads("|table|")
    >>> c = CaptionKeyword.from_source("#+CAPTION: Some table")
    >>> document.body[0].attach_keyword(c)
    >>> len(document.body[0].keywords)
    1
    >>> print(str(document))

    >>> document.body = [c, document.body[0]]
    >>> print(str(document))
    #+CAPTION: Some table
    |table|
    ```
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
        """Set the keyword value."""
        self._value = v
        self.mark_dirty()

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


class CaptionKeyword(AffiliatedKeyword):
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
        """Create a [org_parser.element.CaptionKeyword][] from a ``caption_keyword`` node."""
        optval_node = node.child_by_field_name("optval")
        short = None if optval_node is None else document.source_for(optval_node).decode()
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
        """Set the short caption."""
        self._short = value
        self.mark_dirty()

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


class TblnameKeyword(AffiliatedKeyword):
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
        """Create a [org_parser.element.TblnameKeyword][] from a ``tblname_keyword`` node."""
        elem = cls(value=cls._value_from_node(node, document), parent=parent)
        elem.attach_source(node, document)
        return elem


class ResultsKeyword(AffiliatedKeyword):
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
        """Create a [org_parser.element.ResultsKeyword][] from a ``results_keyword`` node."""
        elem = cls(value=cls._value_from_node(node, document), parent=parent)
        elem.attach_source(node, document)
        return elem


class PlotKeyword(AffiliatedKeyword):
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
        """Create a [org_parser.element.PlotKeyword][] from a ``plot_keyword`` node."""
        elem = cls(value=cls._value_from_node(node, document), parent=parent)
        elem.attach_source(node, document)
        return elem
