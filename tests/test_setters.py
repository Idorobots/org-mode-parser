"""Tests for mutable properties and dirty tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser import load
from org_parser.document import Document, Heading
from org_parser.element import Element
from org_parser.text import CompletionCounter, RichText

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


def test_element_setters_mark_dirty() -> None:
    """Element setters update values and dirty state."""
    element = Element(node_type="paragraph", source_text="old")
    assert element.dirty is False
    element.node_type = "quote_block"
    element.source_text = "new"
    assert element.node_type == "quote_block"
    assert element.source_text == "new"
    assert element.dirty is True


def test_document_setters_mark_dirty() -> None:
    """All mutable document properties set dirty when changed."""
    document = Document(filename="x.org")
    assert document.dirty is False

    title = RichText("Title")
    author = RichText("Author")
    category = RichText("work")
    description = RichText("desc")
    todo = RichText("TODO | DONE")
    keywords = {"LANG": RichText("en")}
    body = [Element(node_type="paragraph", source_text="Body")]
    child = Heading(level=1, document=document, parent=document)

    document.filename = "new.org"
    document.title = title
    document.author = author
    document.category = category
    document.description = description
    document.todo = todo
    document.keywords = keywords
    document.body = body
    document.children = [child]
    document.source = b"* Updated\n"

    assert document.filename == "new.org"
    assert document.title is title
    assert document.author is author
    assert document.category is category
    assert document.description is description
    assert document.todo is todo
    assert document.keywords is keywords
    assert document.body is body
    assert document.children == [child]
    assert document.source == b"* Updated\n"
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
    heading.body = [Element(node_type="paragraph", source_text="Text")]
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
    assert len(heading.body) == 1
    assert heading.parent is document
    assert heading.children == []
    assert heading.document is new_document
    assert heading.dirty is True
    assert document.dirty is True
    assert new_document.dirty is True


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
    element = Element(node_type="paragraph", source_text="text")
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
