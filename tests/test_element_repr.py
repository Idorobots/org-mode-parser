"""Tests for tree-oriented element ``__repr__`` output."""

from __future__ import annotations

from org_parser import loads


def test_list_repr_shows_nested_semantic_items() -> None:
    """List repr exposes nested semantic children instead of source slices."""
    document = loads("- one\n  - child\n")

    rendered = repr(document.body[0])
    assert rendered.startswith("List(\n")
    assert "  items=[" in rendered
    assert "    ListItem(" in rendered
    assert "RichText('one')" in rendered
    assert "source_text" not in rendered


def test_block_repr_shows_embedded_elements() -> None:
    """Container block repr includes parsed nested element objects."""
    document = loads("#+begin_quote\n- one\n#+end_quote\n")

    rendered = repr(document.body[0])
    assert rendered.startswith("QuoteBlock(\n")
    assert "  body=[" in rendered
    assert "    List(" in rendered


def test_block_repr_shows_specific_metadata_fields() -> None:
    """Block repr exposes dedicated metadata fields over begin-line text."""
    document = loads(
        "#+begin_src python -n\n"
        "print('x')\n"
        "#+end_src\n\n"
        "#+begin_warning :foo bar\n"
        "careful\n"
        "#+end_warning\n"
    )

    source_repr = repr(document.body[0])
    assert source_repr.startswith("SourceBlock(")
    assert "language='python'" in source_repr
    assert "switches='-n'" in source_repr
    assert "begin_line" not in source_repr

    special_repr = repr(document.body[2])
    assert special_repr.startswith("SpecialBlock(")
    assert "name='warning'" in special_repr
    assert "parameters=':foo bar'" in special_repr
    assert "begin_line" not in special_repr


def test_drawer_and_table_repr_show_semantic_structure() -> None:
    """Drawer and table reprs expose body rows/cells and nested elements."""
    drawer_document = loads(":X:\n- one\n:END:\n")
    table_document = loads("| a | b |\n")

    drawer_repr = repr(drawer_document.body[0])
    assert drawer_repr.startswith("Drawer(\n")
    assert "  name='X'," in drawer_repr
    assert "    List(" in drawer_repr

    table_repr = repr(table_document.body[0])
    assert table_repr.startswith("Table(\n")
    assert "  rows=[" in table_repr
    assert "    TableRow(" in table_repr
    assert "      TableCell(" in table_repr


def test_document_and_heading_repr_show_semantic_tree() -> None:
    """Document and heading reprs expose nested semantic body/children."""
    document = loads("#+TITLE: T\n\n* H\n- one\n")

    document_repr = repr(document)
    assert document_repr.startswith("Document(\n")
    assert "title=RichText(" in document_repr
    assert "  children=[" in document_repr
    assert "    Heading(" in document_repr

    heading_repr = repr(document.children[0])
    assert heading_repr.startswith("Heading(\n")
    assert "title=RichText('H')" in heading_repr
    assert "  body=[" in heading_repr
    assert "    List(" in heading_repr


def test_leaf_repr_remains_single_line() -> None:
    """Leaf semantic nodes stay compact on one line."""
    document = loads("Paragraph text\n")

    rendered = repr(document.body[0])
    assert rendered == "Paragraph(body=RichText('Paragraph text\\n'))"
