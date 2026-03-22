"""Tests for iterator/sequence behavior across semantic objects."""

from __future__ import annotations

from org_parser import loads
from org_parser.document import Document, Heading
from org_parser.element import Drawer, List, ListItem, QuoteBlock, Table, TableRow
from org_parser.text import PlainText, RichText


def test_document_sequence_uses_all_headings_order() -> None:
    """Document sequence protocol traverses headings including descendants."""
    document = loads(
        "* Top\n" "** Child A\n" "** Child B\n" "*** Grandchild\n" "* Second\n"
    )

    assert len(document) == 5
    assert [heading.title_text for heading in document] == [
        "Top",
        "Child A",
        "Child B",
        "Grandchild",
        "Second",
    ]
    first_heading = document[0]
    assert isinstance(first_heading, Heading)
    assert first_heading.title_text == "Top"
    sub_slice = document[1:3]
    assert isinstance(sub_slice, list)
    assert [heading.title_text for heading in sub_slice] == ["Child A", "Child B"]


def test_heading_sequence_iterates_direct_children() -> None:
    """Heading sequence protocol iterates and indexes direct children."""
    document = loads("* Parent\n** One\n** Two\n")
    heading = document.children[0]

    assert len(heading) == 2
    assert [child.title_text for child in heading] == ["One", "Two"]
    first_child = heading[0]
    assert isinstance(first_child, Heading)
    assert first_child.title_text == "One"


def test_table_and_row_sequence_supports_cell_assignment() -> None:
    """Table rows expose values and support ``table[row][column] = value``."""
    document = loads("| A | B |\n| 1 | 2 |\n")
    assert isinstance(document.body[0], Table)
    table = document.body[0]

    first_row = table[0]
    assert isinstance(first_row, TableRow)
    assert [str(value) for value in first_row] == [" A ", " B "]
    assert str(first_row[0]) == " A "

    second_row = table[1]
    assert isinstance(second_row, TableRow)
    second_row[1] = "9"

    assert str(second_row[1]) == "9"
    assert table.dirty is True
    assert document.dirty is True


def test_list_sequence_iterates_items() -> None:
    """List sequence protocol iterates and indexes list items."""
    document = loads("- one\n- two\n")
    assert isinstance(document.body[0], List)
    parsed = document.body[0]

    assert len(parsed) == 2
    assert isinstance(parsed[0], ListItem)
    assert [str(item.first_line) for item in parsed] == ["one", "two"]


def test_rich_text_sequence_iterates_parts() -> None:
    """RichText sequence protocol exposes constituent inline-object parts."""
    rich_text = RichText([PlainText("a"), PlainText("b")])

    assert len(rich_text) == 2
    assert isinstance(rich_text[0], PlainText)
    assert [str(part) for part in rich_text] == ["a", "b"]


def test_drawer_sequence_iterates_body_elements() -> None:
    """Drawer sequence protocol iterates over drawer body elements."""
    document = loads(":NOTE:\nHello\n#+begin_quote\nQ\n#+end_quote\n:END:\n")
    assert isinstance(document.body[0], Drawer)
    drawer = document.body[0]

    assert len(drawer) == 2
    assert isinstance(drawer[1], QuoteBlock)
    assert [type(element).__name__ for element in drawer] == ["Paragraph", "QuoteBlock"]


def test_list_item_sequence_uses_body_elements() -> None:
    """ListItem sequence protocol follows body-element content."""
    document = loads("- item\n  continuation\n")
    assert isinstance(document.body[0], List)
    parsed = document.body[0]
    item = parsed[0]

    assert len(item) == 1
    assert str(item[0]) == "continuation\n"


def test_container_block_sequence_uses_body_elements() -> None:
    """Container block sequence protocol iterates block body elements."""
    document = loads("#+begin_quote\nInside\n#+end_quote\n")
    assert isinstance(document.body[0], QuoteBlock)
    block = document.body[0]

    assert len(block) == 1
    assert str(block[0]) == "Inside\n"


def test_properties_setitem_accepts_strings_and_rich_text() -> None:
    """Properties accept both rich-text and plain-string assignments."""
    document = loads(":PROPERTIES:\n:ID: old\n:END:\n")
    assert document.properties is not None
    properties = document.properties

    properties["ID"] = "new"
    properties["CATEGORY"] = RichText("work")

    assert str(properties["ID"]) == "new"
    assert str(properties["CATEGORY"]) == "work"
    assert document.dirty is True


def test_programmatic_document_sequence_behavior() -> None:
    """Programmatic documents expose the same heading sequence protocol."""
    document = Document(filename="x.org")
    first = Heading(level=1, document=document, parent=document, title=RichText("One"))
    second = Heading(level=1, document=document, parent=document, title=RichText("Two"))
    document.children = [first, second]

    assert len(document) == 2
    second_heading = document[1]
    assert isinstance(second_heading, Heading)
    assert second_heading.title_text == "Two"
