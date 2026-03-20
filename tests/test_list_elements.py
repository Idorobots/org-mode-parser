"""Tests for semantic plain-list abstractions."""

from __future__ import annotations

from org_parser import loads
from org_parser.element import BlankLine, Drawer, List, ListItem, Paragraph, QuoteBlock
from org_parser.text import RichText


def test_document_body_parses_plain_list_with_item_features() -> None:
    """Indented continuation elements are attached to the owning list item."""
    document = loads(
        "1. [@5] [X] Build release [1/2]\n"
        "  Continue with notes\n"
        "  #+begin_quote\n"
        "  quoted\n"
        "  #+end_quote\n"
    )

    assert isinstance(document.body[0], List)
    parsed = document.body[0]
    assert len(parsed.items) == 1

    item = parsed.items[0]
    assert item.ordered_counter == "1"
    assert item.bullet == "."
    assert item.counter_set == "5"
    assert item.checkbox == "X"
    assert item.first_line is not None
    assert str(item.first_line) == "Build release [1/2]"
    assert len(item.body) == 2
    assert isinstance(item.body[0], Paragraph)
    assert str(item.body[0]) == "Continue with notes\n"
    assert isinstance(item.body[1], QuoteBlock)
    assert item.parent is parsed
    assert item.body[0].parent is item
    assert item.body[1].parent is item


def test_heading_and_drawer_bodies_support_plain_list_elements() -> None:
    """Heading and drawer body extraction return dedicated list elements."""
    document = loads("* H\n- top\n:NOTE:\n- nested\n:END:\n")

    heading = document.children[0]
    assert isinstance(heading.body[0], List)
    assert isinstance(heading.body[1], Drawer)
    drawer = heading.body[1]
    assert isinstance(drawer.body[0], List)


def test_list_item_mutation_marks_list_and_document_dirty() -> None:
    """Mutating list-item first-line content bubbles dirty state upwards."""
    document = loads("- old\n")
    assert isinstance(document.body[0], List)
    parsed = document.body[0]
    item = parsed.items[0]

    item.first_line = RichText("new")

    assert item.dirty is True
    assert parsed.dirty is True
    assert document.dirty is True
    assert str(parsed) == "- new\n"


def test_indented_paragraph_mutation_dirties_owner_list_item() -> None:
    """Mutating attached continuation paragraph bubbles through list ownership."""
    document = loads("- one\n  next\n")
    assert isinstance(document.body[0], List)
    parsed = document.body[0]
    item = parsed.items[0]
    assert len(item.body) == 1
    assert isinstance(item.body[0], Paragraph)
    paragraph = item.body[0]

    paragraph.body.text = "changed\n"

    assert paragraph.dirty is True
    assert item.dirty is True
    assert parsed.dirty is True
    assert document.dirty is True
    assert str(parsed) == "- one\n  changed\n"


def test_list_append_item_supports_mutation_and_adoption() -> None:
    """Appending a new item marks list dirty and adopts ownership."""
    document = loads("- first\n")
    assert isinstance(document.body[0], List)
    parsed = document.body[0]

    parsed.append_item(
        ListItem(
            bullet="-",
            first_line=RichText("second"),
        )
    )

    assert len(parsed.items) == 2
    assert parsed.items[1].parent is parsed
    assert parsed.dirty is True
    assert document.dirty is True
    assert str(parsed) == "- first\n- second\n"


def test_nested_list_items_are_recovered_by_indent() -> None:
    """Indented list items are reconstructed as nested semantic lists."""
    document = loads("- top\n  - child one\n  - child two\n- next\n")

    assert isinstance(document.body[0], List)
    top_list = document.body[0]
    assert len(top_list.items) == 2

    top_item = top_list.items[0]
    assert len(top_item.body) == 1
    assert isinstance(top_item.body[0], List)
    nested_list = top_item.body[0]
    assert len(nested_list.items) == 2
    assert str(nested_list.items[0].first_line) == "child one"
    assert str(nested_list.items[1].first_line) == "child two"


def test_mixed_indent_paragraph_attaches_block_line_and_keeps_tail() -> None:
    """Block line after list item attaches while later tail stays section-level."""
    document = loads("- one\n  continuation\nplain tail\n")

    assert isinstance(document.body[0], List)
    parsed = document.body[0]
    item = parsed.items[0]
    assert len(item.body) == 1
    assert isinstance(item.body[0], Paragraph)
    assert str(item.body[0]) == "continuation\n"
    assert isinstance(document.body[1], Paragraph)
    assert str(document.body[1]) == "plain tail\n"


def test_single_blank_line_keeps_continuation_ownership() -> None:
    """A single blank line does not break continuation attachment."""
    document = loads("- one\n\n  continued\n- two\n")

    assert isinstance(document.body[0], List)
    parsed = document.body[0]
    assert len(parsed.items) == 2
    assert len(parsed.items[0].body) == 2
    assert isinstance(parsed.items[0].body[0], BlankLine)
    assert isinstance(parsed.items[0].body[1], Paragraph)
    assert str(parsed.items[0].body[1]) == "continued\n"


def test_dirty_document_preserves_blank_line_between_list_and_paragraph() -> None:
    """Dirty rendering keeps list-to-paragraph blank-line separators."""
    document = loads("- a\n\nPara\n")

    document.mark_dirty()

    assert str(document) == "- a\n\nPara\n"


def test_dirty_document_preserves_blank_line_between_list_items() -> None:
    """Dirty rendering keeps blank lines that separate list items."""
    document = loads("- a\n\n- b\n")

    document.mark_dirty()

    assert str(document) == "- a\n\n- b\n"


def test_lone_end_after_indented_list_item_recovers_as_paragraph() -> None:
    """A lone indented ``:END:`` after a list item is recovered as paragraph text."""
    document = loads(
        "* TODO Heading\n"
        '  - State "DONE"       from "TODO"       [2014-08-15 Fri 23:25]\n'
        "  :END:\n"
    )

    heading = document.children[0]
    assert isinstance(heading.body[0], List)
    assert isinstance(heading.body[1], Paragraph)
    assert str(heading.body[1]) == ":END:\n"
    assert document.errors == []


def test_block_body_breaks_recovered_lists_on_non_list_nodes() -> None:
    """Paragraphs inside one block split recovered list runs."""
    document = loads("- parent\n  - child a\n  break\n  - child b\n")

    assert isinstance(document.body[0], List)
    parent_item = document.body[0].items[0]
    assert len(parent_item.body) == 3
    assert isinstance(parent_item.body[0], List)
    assert isinstance(parent_item.body[1], Paragraph)
    assert isinstance(parent_item.body[2], List)


def test_consecutive_blocks_of_same_indent_stay_separate() -> None:
    """Recovery does not merge paragraph runs across sibling blocks."""
    document = loads("- one\n  first\n\n  second\n")

    assert isinstance(document.body[0], List)
    item = document.body[0].items[0]
    assert len(item.body) == 3
    assert isinstance(item.body[0], Paragraph)
    assert isinstance(item.body[1], BlankLine)
    assert isinstance(item.body[2], Paragraph)
    assert str(item.body[0]) == "first\n"
    assert str(item.body[2]) == "second\n"


def test_dirty_nested_list_rendering_uses_item_driven_indentation() -> None:
    """Dirty nested list rendering is driven by item stringification."""
    document = loads("- parent\n  - child\n")
    assert isinstance(document.body[0], List)
    parsed = document.body[0]

    parsed.items[0].first_line = RichText("updated")

    assert str(parsed) == "- updated\n  - child\n"


def test_marking_list_dirty_marks_all_items_dirty() -> None:
    """Directly marking a list dirty marks each contained item dirty."""
    document = loads("- one\n- two\n")
    assert isinstance(document.body[0], List)
    parsed = document.body[0]

    assert parsed.items[0].dirty is False
    assert parsed.items[1].dirty is False

    parsed.mark_dirty()

    assert parsed.dirty is True
    assert parsed.items[0].dirty is True
    assert parsed.items[1].dirty is True


def test_dirty_list_indents_non_list_body_elements() -> None:
    """Dirty list rendering indents all non-list body elements by level."""
    document = loads("- one\n  #+begin_quote\n  q\n  #+end_quote\n")
    assert isinstance(document.body[0], List)
    parsed = document.body[0]

    parsed.items[0].first_line = RichText("ONE")

    assert str(parsed) == "- ONE\n  #+begin_quote\n    q\n    #+end_quote\n"


def test_dirty_standalone_list_item_aligns_body_after_bullet_column() -> None:
    """Standalone dirty list items indent continuation body by one step."""
    item = ListItem(
        bullet="-",
        first_line=RichText("List item line"),
        body=[Paragraph(body=RichText("body is aligned to the line text\n"))],
    )

    assert str(item) == "- List item line\n  body is aligned to the line text\n"
