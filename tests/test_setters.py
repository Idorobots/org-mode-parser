"""Tests for mutable properties and dirty tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser import load
from org_parser.document import Document, Heading
from org_parser.element import Element, Keyword, Paragraph
from org_parser.text import CompletionCounter, RichText
from org_parser.time import Timestamp

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def test_rich_text_setter_marks_dirty() -> None:
    """RichText text setter updates value and dirty state."""
    rich_text = RichText("before")
    assert rich_text.dirty is False
    rich_text.text = "after"
    assert rich_text.text == "after"
    assert str(rich_text) == "after"
    assert rich_text.dirty is True


def test_rich_text_mutation_bubbles_to_heading_and_document() -> None:
    """Mutating heading title rich text marks heading and document dirty."""
    document = Document(filename="doc.org")
    heading = Heading(
        level=1, document=document, parent=document, title=RichText("Old")
    )
    assert document.dirty is False
    assert heading.dirty is False
    assert heading.title is not None

    heading.title.text = "New"

    assert heading.title.dirty is True
    assert heading.dirty is True
    assert document.dirty is True


def test_element_parent_setter_does_not_mark_dirty() -> None:
    """Element parent setter updates parent without affecting dirty state."""
    document = Document(filename="doc.org")
    heading = Heading(level=1, document=document, parent=document)
    element = Element(parent=heading)
    assert element.dirty is False
    assert heading.dirty is False
    assert document.dirty is False

    element.parent = heading

    assert element.dirty is False
    assert heading.dirty is False
    assert document.dirty is False


def test_document_setters_mark_dirty() -> None:
    """All mutable document properties set dirty when changed."""
    document = Document(filename="x.org")
    assert document.dirty is False

    title = Keyword(key="TITLE", value=RichText("Title"))
    author = Keyword(key="AUTHOR", value=RichText("Author"))
    category = Keyword(key="CATEGORY", value=RichText("work"))
    description = Keyword(key="DESCRIPTION", value=RichText("desc"))
    todo = Keyword(key="TODO", value=RichText("TODO | DONE"))
    keywords = {"LANG": Keyword(key="LANG", value=RichText("en"))}
    body: list[Element] = [Paragraph(body=RichText("Body\n"))]
    child = Heading(level=1, document=document, parent=document)

    document.filename = "new.org"
    document.keywords = keywords
    document.title = title
    document.author = author
    document.category = category
    document.description = description
    document.todo = todo
    document.body = body
    document.children = [child]

    assert document.filename == "new.org"
    assert document.title is title
    assert document.author is author
    assert document.category is category
    assert document.description is description
    assert document.todo is todo
    assert document.keywords is keywords
    assert document.keywords["TITLE"] is title
    assert document.keywords["AUTHOR"] is author
    assert document.keywords["CATEGORY"] is category
    assert document.keywords["DESCRIPTION"] is description
    assert document.keywords["TODO"] is todo
    assert document.body is body
    assert document.children == [child]
    assert document.dirty is True


def test_keyword_value_mutation_bubbles_to_document() -> None:
    """Mutating keyword value marks keyword and document dirty."""
    document = Document(
        filename="x.org",
        title=Keyword(key="TITLE", value=RichText("Initial")),
    )
    assert document.title is not None
    assert document.dirty is False
    assert document.title.dirty is False

    document.title.value.text = "Changed"

    assert document.title.dirty is True
    assert document.dirty is True


def test_heading_setters_mark_heading_and_document_dirty() -> None:
    """Heading setter mutations mark both heading and document dirty."""
    document = Document(filename="doc.org")
    parent = Heading(level=1, document=document, parent=document)
    heading = Heading(level=2, document=document, parent=parent)
    assert heading.dirty is False
    assert document.dirty is False

    heading.level = 3
    heading.todo = "TODO"
    heading.priority = "A"
    heading.title = RichText("Heading")
    heading.counter = CompletionCounter("1/2")
    heading.tags = ["work", "next"]
    heading.scheduled = Timestamp(
        raw="<2025-03-01 Sat>",
        is_active=True,
        start_year=2025,
        start_month=3,
        start_day=1,
        start_dayname="Sat",
    )
    heading.deadline = Timestamp(
        raw="<2025-03-05 Wed>",
        is_active=True,
        start_year=2025,
        start_month=3,
        start_day=5,
        start_dayname="Wed",
    )
    heading.closed = Timestamp(
        raw="[2025-03-02 Sun 09:00]",
        is_active=False,
        start_year=2025,
        start_month=3,
        start_day=2,
        start_dayname="Sun",
        start_hour=9,
        start_minute=0,
    )
    heading.body = [Paragraph(body=RichText("Text\n"))]
    heading.parent = document
    heading.children = []

    new_document = Document(filename="other.org")
    heading.document = new_document

    assert heading.level == 3
    assert heading.todo == "TODO"
    assert heading.priority == "A"
    assert heading.title == "Heading"
    assert heading.counter == CompletionCounter("1/2")
    assert heading.tags == ["work", "next"]
    assert heading.scheduled is not None
    assert heading.deadline is not None
    assert heading.closed is not None
    assert len(heading.body) == 1
    assert heading.parent is document
    assert heading.children == []
    assert heading.document is new_document
    assert heading.dirty is True
    assert document.dirty is True
    assert new_document.dirty is True


def test_nested_heading_mutation_bubbles_to_root_document() -> None:
    """Child heading mutation marks parent headings and document dirty."""
    document = Document(filename="doc.org")
    parent = Heading(level=1, document=document, parent=document)
    child = Heading(level=2, document=document, parent=parent)

    assert document.dirty is False
    assert parent.dirty is False
    assert child.dirty is False

    child.todo = "DONE"

    assert child.dirty is True
    assert parent.dirty is True
    assert document.dirty is True


def test_paragraph_body_mutation_bubbles_to_owners() -> None:
    """Mutating paragraph body bubbles dirty state up the ownership chain."""
    document = Document(filename="doc.org")
    heading = Heading(level=1, document=document, parent=document)
    paragraph = Paragraph(body=RichText("Before\n"), parent=heading)

    assert document.dirty is False
    assert heading.dirty is False
    assert paragraph.dirty is False

    paragraph.body.text = "After\n"

    assert paragraph.dirty is True
    assert heading.dirty is True
    assert document.dirty is True


def test_parsed_objects_start_clean(example_file: Callable[[str], Path]) -> None:
    """Objects created from parse trees start with dirty=False."""
    document = load(str(example_file("nested-headings-basic.org")))
    assert document.dirty is False
    assert len(document.children) > 0
    assert document.children[0].dirty is False


def test_mark_dirty_methods_mark_objects_programmatically() -> None:
    """Public mark_dirty() APIs mark objects as dirty."""
    document = Document(filename="doc.org")
    heading = Heading(level=1, document=document, parent=document)
    element = Element()
    rich_text = RichText("text")

    assert document.dirty is False
    assert heading.dirty is False
    assert element.dirty is False
    assert rich_text.dirty is False

    rich_text.mark_dirty()
    element.mark_dirty()
    heading.mark_dirty()

    assert rich_text.dirty is True
    assert element.dirty is True
    assert heading.dirty is True
    assert document.dirty is True
