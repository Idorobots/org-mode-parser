"""Tests for strict ``from_source`` convenience constructors."""

from __future__ import annotations

import pytest

from org_parser.document import Document, Heading
from org_parser.element import Element, List, Paragraph
from org_parser.text import Bold, RichText
from org_parser.time import Timestamp


def test_document_from_source_parses_full_document() -> None:
    """Document.from_source parses full Org source text."""
    document = Document.from_source("#+title: Document\n* TODO Some task")
    assert document.title is not None
    assert str(document.title) == "Document"
    assert len(document.children) == 1
    assert document.children[0].todo == "TODO"


def test_heading_from_source_parses_single_heading() -> None:
    """Heading.from_source parses one top-level heading."""
    heading = Heading.from_source("* TODO Some new task")
    assert heading.todo == "TODO"
    assert heading.title is not None
    assert str(heading.title) == "Some new task"


def test_rich_text_from_source_parses_inline_objects() -> None:
    """RichText.from_source parses inline markup from one paragraph."""
    rich_text = RichText.from_source("*this* should /parse/ fine_{+1}")
    assert isinstance(rich_text.parts[0], Bold)
    assert str(rich_text) == "*this* should /parse/ fine_{+1}"


def test_timestamp_from_source_parses_single_active_timestamp() -> None:
    """Timestamp.from_source parses one timestamp without extra text."""
    timestamp = Timestamp.from_source("<2026-03-22 Sun 14:43>")
    assert timestamp.start_year == 2026
    assert timestamp.start_month == 3
    assert timestamp.start_day == 22
    assert timestamp.start_hour == 14
    assert timestamp.start_minute == 43
    assert timestamp.is_active


def test_timestamp_from_source_parses_single_inactive_timestamp() -> None:
    """Timestamp.from_source parses one timestamp without extra text."""
    timestamp = Timestamp.from_source("[2026-03-22 Sun 14:43]")
    assert timestamp.start_year == 2026
    assert timestamp.start_month == 3
    assert timestamp.start_day == 22
    assert timestamp.start_hour == 14
    assert timestamp.start_minute == 43
    assert not timestamp.is_active


def test_element_subclass_from_source_parses_recovered_list() -> None:
    """Element subclass constructors parse strict single-element inputs."""
    parsed_list = List.from_source("- foo\n- bar\n")
    assert len(parsed_list.items) == 2
    assert str(parsed_list.items[0].first_line) == "foo"
    assert str(parsed_list.items[1].first_line) == "bar"


def test_element_base_from_source_returns_single_element() -> None:
    """Element.from_source returns the parsed semantic element."""
    element = Element.from_source("plain text\n")
    assert isinstance(element, Paragraph)
    assert str(element) == "plain text\n"


def test_document_from_source_raises_for_parse_errors() -> None:
    """Document.from_source rejects malformed source that has parse errors."""
    with pytest.raises(ValueError, match="parse errors"):
        Document.from_source("#+TITLE[")


def test_heading_from_source_requires_only_one_heading() -> None:
    """Heading.from_source rejects mixed zeroth-section and heading input."""
    with pytest.raises(ValueError, match="Unexpected parse tree structure"):
        Heading.from_source("#+TITLE: T\n* TODO Task")


def test_rich_text_from_source_requires_paragraph_structure() -> None:
    """RichText.from_source rejects non-paragraph source."""
    with pytest.raises(ValueError, match="Unexpected parse tree structure"):
        RichText.from_source("* TODO Not rich text")


def test_timestamp_from_source_requires_exactly_one_timestamp() -> None:
    """Timestamp.from_source rejects surrounding non-timestamp text."""
    with pytest.raises(ValueError, match="Unexpected parse tree structure"):
        Timestamp.from_source("before <2026-03-22 Sun 14:43>")


def test_element_subclass_from_source_rejects_mismatched_element_type() -> None:
    """Element subclasses reject valid source for a different element class."""
    with pytest.raises(ValueError, match="expected List"):
        List.from_source("plain text\n")


def test_element_subclass_from_source_requires_single_element() -> None:
    """Element.from_source rejects source with multiple semantic elements."""
    with pytest.raises(ValueError, match="Unexpected parse tree structure"):
        List.from_source("- foo\n\nparagraph\n")
