"""Tests for semantic block element abstractions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser import loads
from org_parser.element import (
    BlankLine,
    CenterBlock,
    CommentBlock,
    DynamicBlock,
    ExampleBlock,
    ExportBlock,
    FixedWidthBlock,
    List,
    Paragraph,
    QuoteBlock,
    SourceBlock,
    SpecialBlock,
    Table,
    VerseBlock,
)
from org_parser.text import RichText

if TYPE_CHECKING:
    from collections.abc import Sequence


def _non_blank(elements: Sequence[object]) -> list[object]:
    """Return elements excluding grammar-level blank-line separators."""
    return [element for element in elements if not isinstance(element, BlankLine)]


def test_document_body_uses_dedicated_block_element_types() -> None:
    """Document bodies parse known block nodes into dedicated element classes."""
    document = loads(
        "#+begin_quote\n"
        "quoted\n"
        "#+end_quote\n\n"
        "#+begin_example\n"
        "example\n"
        "#+end_example\n\n"
        "#+begin_src python -n\n"
        "print('x')\n"
        "#+end_src\n\n"
        "#+begin: clocktable :scope subtree\n"
        "| A | B |\n"
        "#+end:\n\n"
        "#+begin_center\n"
        "centered\n"
        "#+end_center\n\n"
        "#+begin_warning\n"
        "warn\n"
        "#+end_warning\n\n"
        "#+begin_comment\n"
        "hidden\n"
        "#+end_comment\n\n"
        "#+begin_export html\n"
        "<p>x</p>\n"
        "#+end_export\n\n"
        "#+begin_verse\n"
        "line\n"
        "#+end_verse\n\n"
        ": fixed\n"
    )

    assert any(isinstance(element, BlankLine) for element in document.body)
    body = _non_blank(document.body)
    assert isinstance(body[0], QuoteBlock)
    assert isinstance(body[1], ExampleBlock)
    assert isinstance(body[2], SourceBlock)
    assert isinstance(body[3], DynamicBlock)
    assert isinstance(body[4], CenterBlock)
    assert isinstance(body[5], SpecialBlock)
    assert isinstance(body[6], CommentBlock)
    assert isinstance(body[7], ExportBlock)
    assert isinstance(body[8], VerseBlock)
    assert isinstance(body[9], FixedWidthBlock)


def test_heading_body_uses_dedicated_block_element_types() -> None:
    """Heading section bodies expose dedicated block element subclasses."""
    document = loads(
        "* H\n"
        "#+begin_quote\n"
        "quoted\n"
        "#+end_quote\n\n"
        "#+begin_src python\n"
        "print('x')\n"
        "#+end_src\n"
    )

    heading = document.children[0]
    assert any(isinstance(element, BlankLine) for element in heading.body)
    body = _non_blank(heading.body)
    assert isinstance(body[0], QuoteBlock)
    assert isinstance(body[1], SourceBlock)


def test_unterminated_example_block_reports_document_error() -> None:
    """Truncated example blocks report one parse error on the document."""
    document = loads("* hurr\n#+begin_example\ndurr\n* derp\n")

    assert len(document.children) == 2
    assert len(document.errors) == 1
    assert document.errors[0].message == "Unterminated block (missing end marker)"


def test_text_block_contents_are_mutable_and_bubble_dirty() -> None:
    """Mutating text-block contents marks both block and owner dirty."""
    document = loads("#+begin_example\nold\n#+end_example\n")

    assert isinstance(document.body[0], ExampleBlock)
    block = document.body[0]
    assert block.dirty is False
    assert document.dirty is False

    block.body = "new"

    assert block.body == "new"
    assert block.dirty is True
    assert document.dirty is True
    assert str(block) == "#+begin_example\nnew\n#+end_example\n"


def test_container_block_contents_are_mutable_and_adopt_parents() -> None:
    """Replacing container contents re-homes parents and marks dirty."""
    document = loads("#+begin_quote\none\n#+end_quote\n")

    assert isinstance(document.body[0], QuoteBlock)
    block = document.body[0]
    block.body = [Paragraph(body=RichText("two\n"))]

    assert isinstance(block.body[0], Paragraph)
    assert block.body[0].parent is block
    assert block.dirty is True
    assert document.dirty is True
    assert str(block) == "#+begin_quote\ntwo\n#+end_quote\n"


def test_container_block_body_setter_accepts_element_and_raw_string() -> None:
    """Container block body setter accepts one element and raw string input."""
    document = loads("#+begin_quote\none\n#+end_quote\n")

    assert isinstance(document.body[0], QuoteBlock)
    block = document.body[0]
    paragraph = Paragraph(body=RichText("two\n"))

    block.body = paragraph

    assert block.body == [paragraph]
    assert block.body[0].parent is block

    block.body = "three"

    assert len(block.body) == 1
    assert isinstance(block.body[0], Paragraph)
    assert str(block.body[0]) == "three"
    assert block.body[0].parent is block
    assert str(block) == "#+begin_quote\nthree\n#+end_quote\n"


def test_container_block_body_append_marks_dirty() -> None:
    """Appending to container block body marks block and document dirty."""
    document = loads("#+begin_quote\none\n#+end_quote\n")

    assert isinstance(document.body[0], QuoteBlock)
    block = document.body[0]
    paragraph = Paragraph(body=RichText("two\n"))
    block.body.append(paragraph)

    assert block.dirty is True
    assert document.dirty is True
    assert paragraph.parent is block


def test_nested_container_content_mutation_bubbles_dirty_state() -> None:
    """Mutating nested content marks the owning block and document dirty."""
    document = loads("#+begin_quote\nold\n#+end_quote\n")
    assert isinstance(document.body[0], QuoteBlock)
    block = document.body[0]
    assert isinstance(block.body[0], Paragraph)

    paragraph = block.body[0]
    paragraph.body.text = "new\n"

    assert paragraph.dirty is True
    assert block.dirty is True
    assert document.dirty is True


def test_block_metadata_fields_are_exposed() -> None:
    """Dedicated block classes expose parsed metadata fields."""
    document = loads(
        "#+begin_src python -n -r\n"
        "print('x')\n"
        "#+end_src\n\n"
        "#+begin_export html :exports code\n"
        "<p>x</p>\n"
        "#+end_export\n\n"
        "#+begin_warning :foo bar\n"
        "careful\n"
        "#+end_warning\n\n"
        "#+begin: clocktable :scope subtree\n"
        "| A | B |\n"
        "#+end:\n"
    )

    body = _non_blank(document.body)
    assert isinstance(body[0], SourceBlock)
    source_block = body[0]
    assert source_block.language == "python"
    assert source_block.switches == "-n -r"
    assert source_block.body == "print('x')\n"

    assert isinstance(body[1], ExportBlock)
    export_block = body[1]
    assert export_block.backend == "html"
    assert export_block.parameters == ":exports code"
    assert export_block.body == "<p>x</p>\n"

    assert isinstance(body[2], SpecialBlock)
    special_block = body[2]
    assert special_block.name == "warning"
    assert special_block.parameters == ":foo bar"

    assert isinstance(body[3], DynamicBlock)
    dynamic_block = body[3]
    assert dynamic_block.name == "clocktable"
    assert dynamic_block.parameters == ":scope subtree"
    assert len(dynamic_block.body) == 1
    assert isinstance(dynamic_block.body[0], Table)


def test_fixed_width_contents_are_mutable() -> None:
    """Fixed-width block lines expose mutable text content."""
    document = loads(": before\n")

    assert isinstance(document.body[0], FixedWidthBlock)
    fixed = document.body[0]
    assert fixed.body == "before"

    fixed.body = "after"

    assert fixed.dirty is True
    assert document.dirty is True
    assert str(fixed) == ": after\n"


def test_adjacent_fixed_width_lines_are_coalesced() -> None:
    """Consecutive fixed-width lines parse as one semantic block."""
    document = loads(": one\n: two\n: three\n")

    assert len(document.body) == 1
    assert isinstance(document.body[0], FixedWidthBlock)
    fixed = document.body[0]
    assert fixed.body == "one\ntwo\nthree"
    assert str(fixed) == ": one\n: two\n: three\n"


def test_fixed_width_area_preserves_empty_colon_lines() -> None:
    """Coalesced fixed-width blocks preserve empty ``:`` lines."""
    document = loads(": first\n:\n: third\n")

    assert isinstance(document.body[0], FixedWidthBlock)
    fixed = document.body[0]
    assert fixed.body == "first\n\nthird"
    assert str(fixed) == ": first\n:\n: third\n"


def test_fixed_width_lines_in_list_item_body_are_coalesced() -> None:
    """Nested list-item fixed-width runs are merged into one block."""
    document = loads("- item\n  : one\n  : two\n")

    assert isinstance(document.body[0], List)
    item = document.body[0].items[0]
    assert len(item.body) == 1
    assert isinstance(item.body[0], FixedWidthBlock)
    assert item.body[0].body == "one\ntwo"
