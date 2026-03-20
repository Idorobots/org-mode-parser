"""Tests for string representations of semantic objects."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser import load
from org_parser.document import load_raw
from org_parser.element import Keyword
from org_parser.text import RichText

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import tree_sitter


def _first_child_of_type(
    node: tree_sitter.Node,
    node_type: str,
) -> tree_sitter.Node | None:
    """Return the first direct child node with a matching type."""
    for child in node.children:
        if child.type == node_type:
            return child
    return None


def test_document_str_clean_is_verbatim_zeroth_section(
    example_file: Callable[[str], Path],
) -> None:
    """Clean Document.__str__ reuses exact zeroth-section source bytes."""
    path = example_file("zeroth-section.org")
    document = load(str(path))
    tree = load_raw(path)
    root = tree.root_node

    zeroth = _first_child_of_type(root, "zeroth_section")
    assert zeroth is not None
    expected = document.source_for(zeroth).decode()
    assert str(document) == expected
    assert "* PRODUCTION" not in str(document)


def test_heading_str_clean_is_verbatim_and_omits_subheadings(
    example_file: Callable[[str], Path],
) -> None:
    """Clean Heading.__str__ reuses source and excludes nested headings."""
    path = example_file("nested-headings-basic.org")
    document = load(str(path))
    heading = document.children[0]

    tree = load_raw(path)
    root = tree.root_node
    node = _first_child_of_type(root, "heading")
    assert node is not None

    first_sub = _first_child_of_type(node, "heading")
    assert first_sub is not None
    heading_source = document.source_for(node)
    end_index = first_sub.start_byte - node.start_byte
    expected = heading_source[:end_index].decode()
    assert str(heading) == expected
    assert "** First sub-heading" not in str(heading)


def test_document_str_dirty_rebuilds_from_fields(
    example_file: Callable[[str], Path],
) -> None:
    """Dirty Document.__str__ is reconstructed from semantic fields."""
    document = load(str(example_file("nested-headings-basic.org")))
    document.keywords = {"LANGUAGE": Keyword(key="LANGUAGE", value=RichText("en"))}
    document.title = Keyword(key="TITLE", value=RichText("Mutated Title"))
    document.author = Keyword(key="AUTHOR", value=RichText("Mutated Author"))

    rendered = str(document)
    assert rendered.startswith("#+TITLE: Mutated Title\n#+AUTHOR: Mutated Author\n")
    assert "#+LANGUAGE: en\n" in rendered
    assert "* First top-level heading" not in rendered


def test_heading_str_dirty_rebuilds_and_omits_children(
    example_file: Callable[[str], Path],
) -> None:
    """Dirty Heading.__str__ is reconstructed and excludes sub-headings."""
    document = load(str(example_file("nested-headings-basic.org")))
    heading = document.children[0]
    heading.todo = "DONE"
    heading.priority = "A"
    heading.tags = ["ops", "critical"]

    rendered = str(heading)
    assert rendered.startswith("* DONE [#A] First top-level heading :ops:critical:\n")
    assert "Section content under the first heading." in rendered
    assert "** First sub-heading" not in rendered


def test_heading_str_dirty_includes_planning_line(
    example_file: Callable[[str], Path],
) -> None:
    """Dirty heading rendering includes canonical planning line order."""
    document = load(str(example_file("planning-basic.org")))
    heading = document.children[3]

    heading.todo = "DONE"

    rendered = str(heading)
    assert (
        "SCHEDULED: <2025-01-01 Wed> DEADLINE: <2025-01-10 Fri> "
        "CLOSED: [2025-01-08 Wed 14:23]\n"
    ) in rendered
