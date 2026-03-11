"""Implementation of table semantic abstractions.

This module provides :class:`Table` and dedicated row/cell abstractions for
both Org tables and Table.el tables.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._element import Element, build_semantic_repr
from org_parser.text._rich_text import RichText

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["Table", "TableCell", "TableRow"]


class TableCell:
    """One mutable table cell.

    Args:
        value: Cell value rich text.
        table: Owning table.
    """

    def __init__(self, *, value: RichText, table: Table) -> None:
        self._value = value
        self._table = table
        self._value.set_parent(table, mark_dirty=False)

    @property
    def value(self) -> RichText:
        """Mutable cell value."""
        return self._value

    @value.setter
    def value(self, value: RichText) -> None:
        """Set cell value and mark the owning table as dirty."""
        self._value = value
        self._value.set_parent(self._table, mark_dirty=False)
        self._table.mark_dirty()

    def set_table(self, table: Table) -> None:
        """Assign a new owning table without marking dirty."""
        self._table = table
        self._value.set_parent(table, mark_dirty=False)

    def __str__(self) -> str:
        """Render cell value as text."""
        return str(self._value)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("TableCell", value=self._value)


class TableRow:
    """One mutable table row.

    Args:
        cells: Row cells for data rows.
        is_rule: Whether this is a horizontal rule row.
        table: Owning table.
    """

    def __init__(self, *, cells: list[TableCell], is_rule: bool, table: Table) -> None:
        self._cells = cells
        self._is_rule = is_rule
        self._table = table
        self._adopt_cells()

    @property
    def cells(self) -> list[TableCell]:
        """Mutable row cells."""
        return self._cells

    @cells.setter
    def cells(self, value: list[TableCell]) -> None:
        """Set row cells and mark the owning table as dirty."""
        self._cells = value
        self._adopt_cells()
        self._table.mark_dirty()

    @property
    def is_rule(self) -> bool:
        """Whether this row is a horizontal rule separator."""
        return self._is_rule

    @is_rule.setter
    def is_rule(self, value: bool) -> None:
        """Set row rule state and mark the owning table as dirty."""
        self._is_rule = value
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
        return build_semantic_repr("TableRow", is_rule=self._is_rule, cells=self._cells)


class Table(Element):
    """Org/Table.el table semantic element.

    Args:
        rows: Mutable table rows.
        formulas: Table formulas without ``#+TBLFM:`` prefix.
        is_tableel: Whether source was parsed as a Table.el table.
        parent: Optional parent owner object.
        source_text: Optional verbatim source text.
    """

    def __init__(
        self,
        *,
        rows: list[TableRow],
        formulas: list[str] | None = None,
        is_tableel: bool = False,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        node_type = "tableel_table" if is_tableel else "org_table"
        super().__init__(node_type=node_type, source_text=source_text, parent=parent)
        self._rows = rows
        self._formulas = formulas if formulas is not None else []
        self._is_tableel = is_tableel
        self._adopt_rows()

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        source: bytes,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Table:
        """Create a :class:`Table` from an ``org_table`` or ``tableel_table`` node."""
        source_text = source[node.start_byte : node.end_byte].decode()
        if node.type == "tableel_table":
            parsed_rows = _parse_tableel_rows(source_text)
            table = cls(
                rows=parsed_rows,
                formulas=[],
                is_tableel=True,
                parent=parent,
                source_text=source_text,
            )
            table._node = node
            table._adopt_rows()
            return table

        table = cls(
            rows=[],
            formulas=[],
            is_tableel=False,
            parent=parent,
            source_text=source_text,
        )
        table._node = node

        rows: list[TableRow] = []
        formulas: list[str] = []
        for child in node.named_children:
            if child.type == "table_row":
                rows.append(_parse_org_table_row(child, source, table))
            elif child.type == "tblfm_line":
                formulas.append(_extract_tblfm_formula(child, source))

        table._rows = rows
        table._formulas = formulas
        table._adopt_rows()
        return table

    @property
    def rows(self) -> list[TableRow]:
        """Mutable table rows."""
        return self._rows

    @rows.setter
    def rows(self, value: list[TableRow]) -> None:
        """Set rows and mark table dirty."""
        self._rows = value
        self._adopt_rows()
        self._mark_dirty()

    @property
    def formulas(self) -> list[str]:
        """Mutable table formulas without ``#+TBLFM:`` prefix."""
        return self._formulas

    @formulas.setter
    def formulas(self, value: list[str]) -> None:
        """Set formulas and mark table dirty."""
        self._formulas = value
        self._mark_dirty()

    @property
    def is_tableel(self) -> bool:
        """Whether source table syntax was Table.el."""
        return self._is_tableel

    def _adopt_rows(self) -> None:
        """Assign this table as owner for all rows and cells."""
        for row in self._rows:
            row.set_table(self)

    def __str__(self) -> str:
        """Render table.

        Clean parse-backed tables preserve original source text. Dirty tables
        are always rendered as aligned Org tables.
        """
        if not self.dirty and self._node is not None:
            return self.source_text
        return _render_org_table(self._rows, self._formulas)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr(
            "Table",
            rows=self._rows,
            formulas=self._formulas,
            is_tableel=self._is_tableel,
        )


def _parse_org_table_row(
    node: tree_sitter.Node, source: bytes, table: Table
) -> TableRow:
    """Parse one ``table_row`` node into :class:`TableRow`."""
    has_rule = any(child.type == "table_rule" for child in node.named_children)
    if has_rule:
        return TableRow(cells=[], is_rule=True, table=table)

    cells: list[TableCell] = []
    for child in node.named_children:
        if child.type != "table_cell":
            continue
        value = RichText.from_nodes(child.named_children, source)
        rich_text = RichText("") if value is None else RichText(str(value).strip())
        cells.append(TableCell(value=rich_text, table=table))
    return TableRow(cells=cells, is_rule=False, table=table)


def _extract_tblfm_formula(node: tree_sitter.Node, source: bytes) -> str:
    """Extract formula text from one ``tblfm_line`` node."""
    line = source[node.start_byte : node.end_byte].decode()
    prefix = "#+TBLFM:"
    if line.upper().startswith(prefix.upper()):
        return line[len(prefix) :].strip()
    return line.strip()


def _parse_tableel_rows(source_text: str) -> list[TableRow]:
    """Parse Table.el grid text into row abstractions."""
    rows: list[TableRow] = []
    dummy_table = Table(rows=[], formulas=[], is_tableel=True)
    for raw_line in source_text.splitlines():
        stripped = raw_line.lstrip()
        if stripped.startswith("+"):
            rows.append(TableRow(cells=[], is_rule=True, table=dummy_table))
            continue
        if not stripped.startswith("|"):
            continue
        pieces = stripped.strip("|").split("|")
        cells = [
            TableCell(value=RichText(piece.strip()), table=dummy_table)
            for piece in pieces
        ]
        rows.append(TableRow(cells=cells, is_rule=False, table=dummy_table))
    return rows


def _render_org_table(rows: list[TableRow], formulas: list[str]) -> str:
    """Render aligned Org table text from rows and formulas."""
    column_count = max((len(row.cells) for row in rows if not row.is_rule), default=0)
    if column_count == 0:
        column_count = 1

    widths = [0] * column_count
    for row in rows:
        if row.is_rule:
            continue
        for idx in range(column_count):
            value = str(row.cells[idx]) if idx < len(row.cells) else ""
            widths[idx] = max(widths[idx], len(value))

    widths = [width if width > 0 else 1 for width in widths]

    parts: list[str] = []
    for row in rows:
        if row.is_rule:
            rule_segments = ["-" * (width + 2) for width in widths]
            parts.append(f"|{'+'.join(rule_segments)}|\n")
            continue

        rendered_cells: list[str] = []
        for idx in range(column_count):
            value = str(row.cells[idx]) if idx < len(row.cells) else ""
            rendered_cells.append(f" {value.ljust(widths[idx])} ")
        parts.append(f"|{'|'.join(rendered_cells)}|\n")

    parts.extend(f"#+TBLFM: {formula}\n" for formula in formulas)

    return "".join(parts)
