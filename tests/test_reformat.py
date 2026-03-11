"""Tests for recursive semantic reformatting helpers."""

from __future__ import annotations

from org_parser import loads
from org_parser.element import List, Paragraph


def test_document_reformat_marks_descendants_dirty() -> None:
    """Document reformat recurses through heading/body descendants."""
    document = loads("#+TITLE: T\n\n* A\nSCHEDULED: <2026-03-10 Tue>\n- one\n")
    heading = document.children[0]
    assert heading.scheduled is not None
    assert isinstance(heading.body[0], List)
    parsed_list = heading.body[0]

    document.reformat()

    assert document.dirty is True
    assert document.title is not None and document.title.dirty is True
    assert heading.dirty is True
    assert heading.title is not None and heading.title.dirty is True
    assert heading.scheduled.dirty is True
    assert parsed_list.dirty is True
    assert parsed_list.items[0].dirty is True


def test_heading_reformat_is_subtree_scoped() -> None:
    """Heading reformat dirties its subtree without touching siblings."""
    document = loads("* A\nSCHEDULED: <2026-03-10 Tue>\n- one\n* B\n- two\n")
    first = document.children[0]
    second = document.children[1]
    assert first.scheduled is not None

    first.reformat()

    assert document.dirty is True
    assert first.dirty is True
    assert first.scheduled.dirty is True
    assert isinstance(first.body[0], List)
    assert first.body[0].items[0].dirty is True
    assert second.dirty is False


def test_element_reformat_marks_rich_text_descendants_dirty() -> None:
    """Element reformat recurses into nested paragraph rich text."""
    document = loads("- one\n  continued\n")
    assert isinstance(document.body[0], List)
    parsed_list = document.body[0]
    item = parsed_list.items[0]
    assert isinstance(item.body[0], Paragraph)
    paragraph = item.body[0]

    parsed_list.reformat()

    assert parsed_list.dirty is True
    assert item.dirty is True
    assert paragraph.dirty is True
    assert paragraph.body.dirty is True
