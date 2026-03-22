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

    title = RichText("Title")
    author = RichText("Author")
    category = RichText("work")
    description = RichText("desc")
    todo = RichText("TODO | DONE")
    keywords = [Keyword(key="LANG", value=RichText("en"))]
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
    assert document.body is body
    assert document.children == [child]
    assert document.dirty is True


def test_keyword_value_mutation_bubbles_to_document() -> None:
    """Mutating keyword value marks keyword and document dirty."""
    document = Document(
        filename="x.org",
        title=RichText("Initial"),
    )
    assert document.title is not None
    assert document.dirty is False
    assert document.title.dirty is False

    document.title.text = "Changed"

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
    heading.heading_tags = ["work", "next"]
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
    assert heading.heading_tags == ["work", "next"]
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


def test_document_tags_setter_marks_dirty() -> None:
    """Setting Document.tags marks the document dirty."""
    document = Document(filename="doc.org")
    assert document.dirty is False
    document.tags = ["work", "project"]
    assert document.dirty is True
    assert document.tags == ["work", "project"]
    assert any(kw.key == "FILETAGS" for kw in document.keywords)


def test_heading_tags_property_is_read_only() -> None:
    """Heading.tags is read-only; assignment raises AttributeError."""
    document = Document(filename="doc.org")
    heading = Heading(level=1, document=document, parent=document)
    try:
        heading.tags = ["x"]  # type: ignore[misc]
        assert False, "Expected AttributeError"  # noqa: B011
    except AttributeError:
        pass


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


# ---------------------------------------------------------------------------
# Heading level adjustment on children assignment
# ---------------------------------------------------------------------------


def test_heading_children_level_adjusted_when_equal_to_parent() -> None:
    """Child level is bumped to parent+1 when it equals the parent level."""
    document = Document(filename="doc.org")
    parent = Heading(level=2, document=document, parent=document)
    child = Heading(level=2, document=document, parent=document)

    parent.children = [child]

    assert child.level == 3
    assert child.dirty is True
    assert parent.dirty is True
    assert document.dirty is True


def test_heading_children_level_adjusted_when_lower_than_parent() -> None:
    """Child level is shifted to parent+1 when it is below the parent level."""
    document = Document(filename="doc.org")
    parent = Heading(level=3, document=document, parent=document)
    child = Heading(level=1, document=document, parent=document)

    parent.children = [child]

    assert child.level == 4  # parent.level + 1


def test_heading_children_level_unchanged_when_already_sufficient() -> None:
    """Child level is left unchanged when it is already greater than parent level."""
    document = Document(filename="doc.org")
    parent = Heading(level=1, document=document, parent=document)
    child = Heading(level=3, document=document, parent=document)

    parent.children = [child]

    assert child.level == 3  # no change needed
    assert child.dirty is False  # not marked dirty — level did not change
    assert parent.dirty is True  # parent is always marked dirty by the setter


def test_heading_children_level_minimum_is_parent_plus_one() -> None:
    """Child at exactly parent+1 is the boundary: no adjustment, no dirty."""
    document = Document(filename="doc.org")
    parent = Heading(level=2, document=document, parent=document)
    child = Heading(level=3, document=document, parent=document)

    parent.children = [child]

    assert child.level == 3
    assert child.dirty is False


def test_heading_children_grandchildren_shift_by_same_delta() -> None:
    """Grandchildren shift by the same delta as the child, preserving structure."""
    document = Document(filename="doc.org")
    parent = Heading(level=2, document=document, parent=document)
    child = Heading(level=2, document=document, parent=document)
    grandchild = Heading(level=3, document=document, parent=child)
    # Set grandchild as child's child via public setter; no level adjustment fires
    # here because grandchild.level(3) > child.level(2).
    child.children = [grandchild]

    parent.children = [child]

    # child shifted by delta=1 (from 2 → 3); grandchild shifted by same delta (3 → 4).
    assert child.level == 3
    assert grandchild.level == 4
    assert child.dirty is True
    assert grandchild.dirty is True


def test_heading_children_multiple_children_adjusted_independently() -> None:
    """Each child is adjusted independently relative to the shared parent level."""
    document = Document(filename="doc.org")
    parent = Heading(level=2, document=document, parent=document)
    low = Heading(level=1, document=document, parent=document)
    exact = Heading(level=3, document=document, parent=document)
    high = Heading(level=5, document=document, parent=document)

    parent.children = [low, exact, high]

    assert low.level == 3  # shifted from 1 to 3
    assert exact.level == 3  # already at parent+1 = 3 — no change
    assert high.level == 5  # already above parent+1 — no change
    assert low.dirty is True
    assert exact.dirty is False
    assert high.dirty is False


def test_heading_children_parent_set_correctly_after_assignment() -> None:
    """After children assignment each child's parent points to the heading."""
    document = Document(filename="doc.org")
    parent = Heading(level=1, document=document, parent=document)
    child = Heading(level=5, document=document, parent=document)

    parent.children = [child]

    assert child.parent is parent


def test_document_children_level_adjusted_below_one() -> None:
    """Document enforces a minimum heading level of 1 for its children."""
    document = Document(filename="doc.org")
    heading = Heading(level=0, document=document, parent=document)

    document.children = [heading]

    assert heading.level == 1
    assert heading.dirty is True


def test_document_children_level_one_is_unchanged() -> None:
    """A level-1 heading attached to a document is not modified."""
    document = Document(filename="doc.org")
    heading = Heading(level=1, document=document, parent=document)

    document.children = [heading]

    assert heading.level == 1
    assert heading.dirty is False


def test_document_children_level_above_one_is_unchanged() -> None:
    """A level-3 heading attached to a document is accepted as-is."""
    document = Document(filename="doc.org")
    heading = Heading(level=3, document=document, parent=document)

    document.children = [heading]

    assert heading.level == 3
    assert heading.dirty is False


def test_document_children_grandchildren_shift_with_heading() -> None:
    """When a level-0 heading is shifted, its children shift by the same delta."""
    document = Document(filename="doc.org")
    heading = Heading(level=0, document=document, parent=document)
    child = Heading(level=1, document=document, parent=heading)
    # Wire child under heading via public setter; no adjustment fires because
    # child.level(1) > heading.level(0), so child stays clean.
    heading.children = [child]

    document.children = [heading]

    assert heading.level == 1  # 0 → 1 (delta=1)
    assert child.level == 2  # 1 → 2 (same delta)
    assert heading.dirty is True
    assert child.dirty is True


def test_heading_children_dirty_bubbles_to_document() -> None:
    """Level adjustment on attached children bubbles dirty up to the document."""
    document = Document(filename="doc.org")
    parent = Heading(level=1, document=document, parent=document)
    child = Heading(level=1, document=document, parent=document)

    assert document.dirty is False

    parent.children = [child]

    assert document.dirty is True
