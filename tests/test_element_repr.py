"""Tests for tree-oriented element ``__repr__`` output."""

from __future__ import annotations

from org_parser import loads


def test_list_repr_shows_nested_semantic_items() -> None:
    """List repr exposes nested semantic children instead of source slices."""
    document = loads("- one\n  - child\n")

    rendered = repr(document.body[0])
    assert "List(items=[" in rendered
    assert "ListItem(" in rendered
    assert "RichText('one')" in rendered
    assert "source_text" not in rendered


def test_block_repr_shows_embedded_elements() -> None:
    """Container block repr includes parsed nested element objects."""
    document = loads("#+begin_quote\n- one\n#+end_quote\n")

    rendered = repr(document.body[0])
    assert "QuoteBlock(" in rendered
    assert "body=[" in rendered
    assert "List(items=[" in rendered


def test_drawer_and_table_repr_show_semantic_structure() -> None:
    """Drawer and table reprs expose body rows/cells and nested elements."""
    drawer_document = loads(":X:\n- one\n:END:\n")
    table_document = loads("| a | b |\n")

    drawer_repr = repr(drawer_document.body[0])
    assert "Drawer(name='X'" in drawer_repr
    assert "List(items=[" in drawer_repr

    table_repr = repr(table_document.body[0])
    assert "Table(rows=[" in table_repr
    assert "TableRow(" in table_repr
    assert "TableCell(" in table_repr


def test_document_and_heading_repr_show_semantic_tree() -> None:
    """Document and heading reprs expose nested semantic body/children."""
    document = loads("#+TITLE: T\n\n* H\n- one\n")

    document_repr = repr(document)
    assert "Document(" in document_repr
    assert "title=RichText(" in document_repr
    assert "children=[Heading(" in document_repr

    heading_repr = repr(document.children[0])
    assert "Heading(" in heading_repr
    assert "title=RichText('H')" in heading_repr
    assert "body=[List(items=[" in heading_repr
