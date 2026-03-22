"""Tests for top-level load/loads/dump/dumps helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from org_parser import Document, dump, dumps, load, loads

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def test_load_returns_document(example_file: Callable[[str], Path]) -> None:
    """load() parses an example file into a Document."""
    path = example_file("simple.org")
    document = load(str(path))
    assert isinstance(document, Document)
    assert document.filename == str(path)


def test_loads_without_filename_assigns_empty_filename(
    example_file: Callable[[str], Path],
) -> None:
    """loads() sets an empty filename when none is provided."""
    text = example_file("simple.org").read_text()
    document = loads(text)
    assert document.filename == ""


def test_loads_with_filename_assigns_filename(
    example_file: Callable[[str], Path],
) -> None:
    """loads() assigns the provided filename."""
    text = example_file("simple.org").read_text()
    document = loads(text, "in-memory.org")
    assert document.filename == "in-memory.org"


def test_dumps_returns_original_source(example_file: Callable[[str], Path]) -> None:
    """dumps() returns the original Org text for loaded files."""
    path = example_file("nested-headings-basic.org")
    expected = path.read_text()
    document = load(str(path))
    assert dumps(document) == expected


def test_dump_uses_document_filename(tmp_path: Path) -> None:
    """dump() writes to document.filename when no explicit filename is passed."""
    target = tmp_path / "output.org"
    document = loads("* Heading\n", str(target))
    dump(document)
    assert target.read_text() == "* Heading\n"


def test_dump_uses_explicit_filename_override(tmp_path: Path) -> None:
    """dump() prefers an explicit filename over document.filename."""
    original = tmp_path / "original.org"
    override = tmp_path / "override.org"
    document = loads("* Heading\n", str(original))
    dump(document, str(override))
    assert not original.exists()
    assert override.read_text() == "* Heading\n"


def test_dump_raises_when_no_filename_available() -> None:
    """dump() raises when both explicit and document filename are empty."""
    document = loads("* Heading\n")
    with pytest.raises(ValueError, match="No output filename provided"):
        dump(document)


def test_dumps_dirty_document_includes_mutated_heading(
    example_file: Callable[[str], Path],
) -> None:
    """dumps() reflects heading mutations in a dirty document."""
    document = load(str(example_file("nested-headings-basic.org")))
    document.children[0].todo = "TODO"

    result = dumps(document)

    assert "* TODO First top-level heading" in result
    assert "** First sub-heading" in result
    assert "* Second top-level heading" in result


def test_dumps_dirty_zeroth_section_still_includes_all_headings(
    example_file: Callable[[str], Path],
) -> None:
    """dumps() includes all headings even when only the zeroth section is dirty."""
    from org_parser.element import Keyword
    from org_parser.text import RichText

    document = load(str(example_file("nested-headings-basic.org")))
    document.keywords = [Keyword(key="AUTHOR", value=RichText("Alice"))]

    result = dumps(document)

    assert "#+AUTHOR: Alice" in result
    assert "* First top-level heading" in result
    assert "** First sub-heading" in result
    assert "* Second top-level heading" in result
