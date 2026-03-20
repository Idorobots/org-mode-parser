"""Tests for table semantic abstractions."""

from __future__ import annotations

from org_parser import loads
from org_parser.element import Table, TableRow, TableRuleRow
from org_parser.text import RichText


def test_org_table_parses_rows_cells_and_formulas() -> None:
    """Org tables expose rows, cells, and TBLFM formulas."""
    document = loads("| A | B |\n" "|---+---|\n" "| 1 | 2 |\n" "#+TBLFM: $2=$1+1\n")

    assert isinstance(document.body[0], Table)
    table = document.body[0]
    assert table.is_tableel is False
    assert len(table.rows) == 3
    assert isinstance(table.rows[0], TableRow)
    assert isinstance(table.rows[1], TableRuleRow)
    assert isinstance(table.rows[2], TableRow)
    assert table.rows[1].raw == "|---+---|"
    row0 = table.rows[0]
    row2 = table.rows[2]
    assert isinstance(row0, TableRow)
    assert isinstance(row2, TableRow)
    assert str(row0.cells[0].value) == " A "
    assert str(row2.cells[1].value) == " 2 "
    assert table.formulas == ["$2=$1+1"]
    assert row0.cells[0].value.parent is table


def test_tableel_table_is_supported_in_body() -> None:
    """Table.el fragments are represented as table elements."""
    document = loads(
        "+----------+----------+\n"
        "| Column A | Column B |\n"
        "+----------+----------+\n"
    )

    assert any(
        isinstance(element, Table) and element.is_tableel for element in document.body
    )


def test_dirty_table_renders_as_aligned_org_table() -> None:
    """Dirty tables are rendered in aligned Org table syntax."""
    document = loads("| Name | Age |\n|------+-----|\n| Al | 9 |\n")
    assert isinstance(document.body[0], Table)
    table = document.body[0]

    row2 = table.rows[2]
    assert isinstance(row2, TableRow)
    row2.cells[0].value = RichText("Alice")

    assert table.dirty is True
    assert str(table) == "| Name  | Age |\n|-------+-----|\n| Alice | 9   |\n"


def test_table_row_mutation_marks_table_dirty() -> None:
    """Mutating a cell value marks the owning table as dirty."""
    document = loads("| A |\n| B |\n")
    assert isinstance(document.body[0], Table)
    table = document.body[0]
    assert table.dirty is False

    row0 = table.rows[0]
    assert isinstance(row0, TableRow)
    row0.cells[0].value = RichText("Z")

    assert table.dirty is True
