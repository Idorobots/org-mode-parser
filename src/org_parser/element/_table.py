"""Implementation of table semantic abstractions.

This module provides [org_parser.element.Table][] for Org tables,
[org_parser.element.TableEl][] for Table.el grids, and dedicated row/cell
abstractions for Org table rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import node_source
from org_parser._nodes import (
    ORG_TABLE,
    TABLE_CELL,
    TABLE_ROW,
    TABLE_RULE,
    TABLEEL_TABLE,
    TBLFM_LINE,
)
from org_parser.element._element import Element, build_semantic_repr
from org_parser.text._rich_text import RichText, coerce_rich_text

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["Table", "TableCell", "TableEl", "TableRow", "TableRuleRow"]


class TableCell:
    """One mutable table cell.

    Args:
        value: Cell value rich text.
        table: Owning table.

    Example:
    ```python
    >>> from org_parser import loads
    >>> document = loads('''
    ... | 1 | 2 |
    ... | 3 | 4 |
    ... ''')
    >>> document.body[0].rows[1].cells[1]
    '4'
    ```
    """

    def __init__(self, *, value: RichText | str, table: Table) -> None:
        self._value = coerce_rich_text(value)
        self._table = table
        self._value.parent = table

    @property
    def value(self) -> RichText:
        """Mutable cell value."""
        return self._value

    @value.setter
    def value(self, value: RichText | str) -> None:
        """Set cell value."""
        self._value = coerce_rich_text(value)
        self._value.parent = self._table
        self._table.mark_dirty()

    def set_table(self, table: Table) -> None:
        """Assign a new owning table without marking dirty."""
        self._table = table
        self._value.parent = table

    def __str__(self) -> str:
        """Render cell value as text."""
        return str(self._value)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("TableCell", value=self._value)


class TableRow:
    """One mutable data row in a table.

    Args:
        cells: Row cells.
        table: Owning table.

    Example:
    ```python
    >>> from org_parser import loads
    >>> document = loads('''
    ... | 1 | 2 |
    ... | 3 | 4 |
    ... ''')
    >>> len(document.body[0].rows[1])
    2
    ```
    """

    def __init__(self, *, cells: list[TableCell], table: Table) -> None:
        self._cells = cells
        self._table = table
        self._adopt_cells()

    @property
    def cells(self) -> list[TableCell]:
        """Mutable row cells."""
        return self._cells

    @cells.setter
    def cells(self, value: list[TableCell]) -> None:
        """Set row cells."""
        self._cells = value
        self._adopt_cells()
        self._table.mark_dirty()

    def set_table(self, table: Table) -> None:
        """Assign a new owning table without marking dirty."""
        self._table = table
        self._adopt_cells()

    def _adopt_cells(self) -> None:
        """Assign table ownership to all cells."""
        for cell in self._cells:
            cell.set_table(self._table)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("TableRow", cells=self._cells)

    def __iter__(self) -> Iterator[RichText]:
        """Iterate over column values in this row."""
        return (cell.value for cell in self._cells)

    def __len__(self) -> int:
        """Return number of columns in this row."""
        return len(self._cells)

    def __getitem__(self, index: int | slice) -> RichText | list[RichText]:
        """Return one column value (or value slice) from this row."""
        if isinstance(index, slice):
            return [cell.value for cell in self._cells[index]]
        return self._cells[index].value

    def __setitem__(self, index: int, value: RichText | str) -> None:
        """Set one column value."""
        self._cells[index].value = coerce_rich_text(value)


class TableRuleRow:
    """A horizontal rule row in a table (e.g. ``|---+---|``).

    Stores the raw source text of the rule so the original formatting is
    preserved and accessible for inspection.

    Args:
        raw: Raw source text of the rule row (e.g. ``|---+---|``).
        table: Owning table.
    """

    def __init__(self, *, raw: str, table: Table) -> None:
        self._raw = raw
        self._table = table

    @property
    def raw(self) -> str:
        """Raw source text of the rule row."""
        return self._raw

    def set_table(self, table: Table) -> None:
        """Assign a new owning table without marking dirty."""
        self._table = table

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("TableRuleRow", raw=self._raw)


class Table(Element):
    """Org table semantic element.

    Args:
        rows: Mutable table rows (data rows and rule rows).
        formulas: Table formulas without ``#+TBLFM:`` prefix.
        parent: Optional parent owner object.

    Example:
    ```python
    >>> from org_parser import loads
    >>> document = loads('''
    ... | 1 | 2 |
    ... | 3 | 4 |
    ... ''')
    >>> document.body[0][1][1] = 5
    >>> print(str(document))
    | 1 | 2 |
    | 3 | 5 |
    ```
    """

    def __init__(
        self,
        *,
        rows: list[TableRow | TableRuleRow],
        formulas: Sequence[str] = (),
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._rows = rows
        self._formulas = list(formulas)
        self._adopt_rows()

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Table:
        """Create a [org_parser.element.Table][] from an ``org_table`` node."""
        if node.type != ORG_TABLE:
            msg = f"Expected {ORG_TABLE!r} node, got {node.type!r}"
            raise ValueError(msg)
        table = cls(
            rows=[],
            formulas=[],
            parent=parent,
        )
        table.attach_source(node, document)

        rows: list[TableRow | TableRuleRow] = []
        formulas: list[str] = []
        for child in node.named_children:
            if child.type == TABLE_ROW:
                rows.append(_parse_org_table_row(child, table, document))
            elif child.type == TBLFM_LINE:
                formulas.append(_extract_tblfm_formula(child, document))

        table._rows = rows
        table._formulas = formulas
        table._adopt_rows()
        return table

    @property
    def rows(self) -> list[TableRow | TableRuleRow]:
        """Mutable table rows (data rows and rule rows)."""
        return self._rows

    @rows.setter
    def rows(self, value: list[TableRow | TableRuleRow]) -> None:
        """Set rows."""
        self._rows = value
        self._adopt_rows()
        self.mark_dirty()

    @property
    def formulas(self) -> list[str]:
        """Mutable table formulas without ``#+TBLFM:`` prefix.

        Example:
        ```python
        >>> from org_parser import loads
        >>> document = loads('''
        ... | 1 | 2 |
        ... | 3 | 4 |
        ... #+TBLFM: @1$1=5
        ... ''')
        >>> document.body[0].formulas
        ['@1$1=5']
        ```
        """
        return self._formulas

    @formulas.setter
    def formulas(self, value: list[str]) -> None:
        """Set formulas."""
        self._formulas = value
        self.mark_dirty()

    def _adopt_rows(self) -> None:
        """Assign this table as owner for all rows and cells."""
        for row in self._rows:
            row.set_table(self)

    def __str__(self) -> str:
        """Render table.

        Clean parse-backed tables preserve original source text. Dirty tables
        are always rendered as aligned Org tables.
        """
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        return _render_org_table(self._rows, self._formulas)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr(
            "Table",
            rows=self._rows,
            formulas=self._formulas,
        )

    def __iter__(self) -> Iterator[TableRow | TableRuleRow]:
        """Iterate over table rows."""
        return iter(self._rows)

    def __len__(self) -> int:
        """Return number of rows in this table."""
        return len(self._rows)

    def __getitem__(
        self,
        index: int | slice,
    ) -> TableRow | TableRuleRow | list[TableRow | TableRuleRow]:
        """Return one table row (or row slice)."""
        return self._rows[index]

    def __setitem__(self, index: int, value: TableRow | TableRuleRow) -> None:
        """Replace one table row."""
        self._rows[index] = value
        value.set_table(self)
        self.mark_dirty()


class TableEl(Element):
    """Opaque Table.el grid semantic element."""

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> TableEl:
        """Create a [org_parser.element.TableEl][] from a ``tableel_table`` node."""
        if node.type != TABLEEL_TABLE:
            msg = f"Expected {TABLEEL_TABLE!r} node, got {node.type!r}"
            raise ValueError(msg)
        tableel = cls(parent=parent)
        tableel.attach_source(node, document)
        return tableel

    def __str__(self) -> str:
        """Render the original Table.el grid text."""
        if self._node is None or self._document is None:
            return ""
        return node_source(self._node, self._document)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("TableEl")


def _parse_org_table_row(
    node: tree_sitter.Node,
    table: Table,
    document: Document,
) -> TableRow | TableRuleRow:
    """Parse one ``table_row`` node into a regular or rule row."""
    has_rule = any(child.type == TABLE_RULE for child in node.named_children)
    if has_rule:
        raw_source = document.source_for(node).decode()
        raw = raw_source.rstrip("\n")
        return TableRuleRow(raw=raw, table=table)

    cells: list[TableCell] = []
    for child in node.named_children:
        if child.type != TABLE_CELL:
            continue
        value = RichText.from_nodes(child.named_children, document=document)
        cells.append(TableCell(value=value, table=table))
    return TableRow(cells=cells, table=table)


def _extract_tblfm_formula(
    node: tree_sitter.Node,
    document: Document,
) -> str:
    """Extract formula text from one ``tblfm_line`` node."""
    line = document.source_for(node).decode()
    prefix = "#+TBLFM:"
    if line.upper().startswith(prefix.upper()):
        return line[len(prefix) :].strip()
    return line.strip()


def _render_org_table(rows: list[TableRow | TableRuleRow], formulas: list[str]) -> str:
    """Render aligned Org table text from rows and formulas."""
    column_count = max(
        (len(row.cells) for row in rows if isinstance(row, TableRow)),
        default=0,
    )
    if column_count == 0:
        column_count = 1

    widths = [0] * column_count
    for row in rows:
        if isinstance(row, TableRuleRow):
            continue
        for idx in range(column_count):
            value = str(row.cells[idx]).strip() if idx < len(row.cells) else ""
            widths[idx] = max(widths[idx], len(value))

    widths = [width if width > 0 else 1 for width in widths]

    parts: list[str] = []
    for row in rows:
        if isinstance(row, TableRuleRow):
            rule_segments = ["-" * (width + 2) for width in widths]
            parts.append(f"|{'+'.join(rule_segments)}|\n")
            continue

        rendered_cells: list[str] = []
        for idx in range(column_count):
            value = str(row.cells[idx]).strip() if idx < len(row.cells) else ""
            rendered_cells.append(f" {value.ljust(widths[idx])} ")
        parts.append(f"|{'|'.join(rendered_cells)}|\n")

    parts.extend(f"#+TBLFM: {formula}\n" for formula in formulas)

    return "".join(parts)
