"""Tests for rich text inline object abstractions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser import load, loads
from org_parser.document import Document, load_raw
from org_parser.text import (
    AngleLink,
    Bold,
    Citation,
    Code,
    CompletionCounter,
    ExportSnippet,
    FootnoteReference,
    InlineSourceBlock,
    Italic,
    LineBreak,
    PlainLink,
    PlainText,
    RadioTarget,
    RegularLink,
    RichText,
    StrikeThrough,
    Target,
    Underline,
    Verbatim,
)
from org_parser.time import Timestamp

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import tree_sitter


def _find_first_paragraph_with_prefix(
    root: tree_sitter.Node,
    source: bytes,
    prefix: str,
) -> tree_sitter.Node:
    """Find first paragraph node whose text starts with *prefix*."""
    stack: list[tree_sitter.Node] = [root]
    while stack:
        node = stack.pop()
        if node.type == "paragraph":
            text = source[node.start_byte : node.end_byte].decode()
            if text.startswith(prefix):
                return node
        stack.extend(reversed(node.children))
    raise AssertionError(f"Paragraph starting with {prefix!r} not found")


def _find_first_heading_title_node_with_type(
    root: tree_sitter.Node,
    target_type: str,
) -> tree_sitter.Node:
    """Find the first heading-title child node of *target_type*."""
    stack: list[tree_sitter.Node] = [root]
    while stack:
        node = stack.pop()
        if node.type == "heading":
            for child in node.children_by_field_name("title"):
                if child.type == target_type:
                    return child
        stack.extend(reversed(node.children))
    raise AssertionError(f"Heading title node of type {target_type!r} not found")


def _find_first_node_with_type(
    root: tree_sitter.Node, target_type: str
) -> tree_sitter.Node:
    """Find the first node in the tree with *target_type*."""
    stack: list[tree_sitter.Node] = [root]
    while stack:
        node = stack.pop()
        if node.type == target_type:
            return node
        stack.extend(reversed(node.children))
    raise AssertionError(f"Node of type {target_type!r} not found")


def test_rich_text_from_paragraph_parses_inline_objects(
    example_file: Callable[[str], Path],
) -> None:
    """RichText.from_node parses mixed inline objects in paragraphs."""
    path = example_file("inline-markup-basic.org")
    source = path.read_bytes()
    document = load(str(path))
    tree = load_raw(path)
    paragraph = _find_first_paragraph_with_prefix(tree.root_node, source, "Markup mid-")
    rich_text = RichText.from_node(paragraph, document=document)

    object_types = {type(part) for part in rich_text.parts}
    assert PlainText in object_types
    assert Bold in object_types
    assert Italic in object_types
    assert Underline in object_types
    assert rich_text.dirty is False


def test_rich_text_from_nodes_parses_heading_title_objects(
    example_file: Callable[[str], Path],
) -> None:
    """RichText.from_node parses heading title inline object nodes."""
    path = example_file("export-snippet-basic.org")
    document = load(str(path))
    tree = load_raw(path)
    snippet = _find_first_heading_title_node_with_type(tree.root_node, "export_snippet")
    rich_text = RichText.from_node(snippet, document=document)
    assert len(rich_text.parts) == 1
    assert isinstance(rich_text.parts[0], ExportSnippet)


def test_rich_text_clean_str_is_verbatim_source(
    example_file: Callable[[str], Path],
) -> None:
    """Clean RichText stringification reuses verbatim source slice."""
    path = example_file("footnote-basic.org")
    source = path.read_bytes()
    document = load(str(path))
    tree = load_raw(path)
    paragraph = _find_first_paragraph_with_prefix(
        tree.root_node, source, "An inline foot"
    )
    rich_text = RichText.from_node(paragraph, document=document)
    expected = source[paragraph.start_byte : paragraph.end_byte].decode()
    assert str(rich_text) == expected


def test_rich_text_mutation_marks_dirty_and_reconstructs(
    example_file: Callable[[str], Path],
) -> None:
    """Mutations switch RichText to reconstructed rendering mode."""
    path = example_file("inline-markup-basic.org")
    source = path.read_bytes()
    document = load(str(path))
    tree = load_raw(path)
    paragraph = _find_first_paragraph_with_prefix(tree.root_node, source, "*bold text*")
    rich_text = RichText.from_node(paragraph, document=document)

    rich_text.prepend(PlainText("START "))
    rich_text.append(PlainText(" END"))
    rich_text.insert(1, PlainText("MID "))

    assert rich_text.dirty is True
    assert str(rich_text).startswith("START MID ")
    assert str(rich_text).endswith(" END")


def test_paragraph_plain_text_children_keep_trailing_newlines(tmp_path: Path) -> None:
    """RichText built from paragraphs preserves line newlines."""
    content = "This is some text:\nMore text\nMore text\n"
    path = tmp_path / "multiline-paragraph.org"
    path.write_text(content, encoding="utf-8")

    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)

    assert str(rich_text) == content
    newline_parts = [
        part
        for part in rich_text.parts
        if isinstance(part, PlainText) and str(part) == "\n"
    ]
    assert len(newline_parts) == 3


def test_programmatic_rich_text_construction_uses_public_objects() -> None:
    """Programmatic construction with public inline object classes works."""
    rich_text = RichText(
        [
            PlainText("A "),
            Bold([PlainText("bold")]),
            PlainText(" "),
            Italic([PlainText("italic")]),
            PlainText(" "),
            Underline([PlainText("under")]),
            PlainText(" "),
            StrikeThrough([PlainText("gone")]),
            PlainText(" "),
            Verbatim("raw"),
            PlainText(" "),
            Code("x()"),
            PlainText(" "),
            CompletionCounter("2/5"),
            PlainText(" "),
            PlainLink("https", "//example.org"),
            PlainText(" "),
            AngleLink("//example.org", "https"),
            PlainText(" "),
            RegularLink("id:abc", [PlainText("desc")]),
            PlainText(" "),
            Target("anchor"),
            PlainText(" "),
            RadioTarget([PlainText("radio")]),
            PlainText(" "),
            Timestamp(
                raw="<2025-01-01 Wed>",
                is_active=True,
                start_year=2025,
                start_month=1,
                start_day=1,
                start_dayname="Wed",
            ),
            PlainText(" "),
            FootnoteReference(label="a", definition=[PlainText("d")]),
            PlainText(" "),
            Citation(body="@k", style="t"),
            PlainText(" "),
            InlineSourceBlock(language="python", headers=":results", body="1+1"),
            PlainText(" "),
            ExportSnippet("html", "<b>"),
            PlainText(" "),
            LineBreak(),
        ]
    )
    expected = (
        "A *bold* /italic/ _under_ +gone+ =raw= ~x()~ [2/5] https://example.org "
        "<https://example.org> [[id:abc][desc]] <<anchor>> <<<radio>>> "
        "<2025-01-01 Wed> [fn:a:d] [cite/t:@k] src_python[:results]{1+1} "
        "@@html:<b>@@ \\\\"
    )
    assert str(rich_text) == expected


def test_timestamp_from_node_exposes_components(
    example_file: Callable[[str], Path],
) -> None:
    """Timestamp values expose start/end/components from the parse tree."""
    path = example_file("timestamps-advanced.org")
    source = path.read_bytes()
    tree = load_raw(path)
    document = Document.from_tree(tree, path.name, source)
    timestamp_node = _find_first_node_with_type(tree.root_node, "timestamp")

    timestamp = Timestamp.from_node(timestamp_node, document)

    assert timestamp.is_active is True
    assert timestamp.start_year == 2025
    assert timestamp.start_month == 3
    assert timestamp.start_day == 15
    assert timestamp.start_hour is None
    assert timestamp.start_minute is None
    assert timestamp.end is None
    assert timestamp.to_datetime() == timestamp.start


def test_timestamp_from_node_with_range_has_end(
    example_file: Callable[[str], Path],
) -> None:
    """Range timestamps expose both start and end datetimes."""
    path = example_file("timestamps-advanced.org")
    source = path.read_bytes()
    tree = load_raw(path)
    document = Document.from_tree(tree, path.name, source)

    stack: list[tree_sitter.Node] = [tree.root_node]
    range_timestamp_node: tree_sitter.Node | None = None
    while stack:
        node = stack.pop()
        if node.type == "timestamp":
            timestamp = Timestamp.from_node(node, document)
            if timestamp.end is not None:
                range_timestamp_node = node
                break
        stack.extend(reversed(node.children))

    assert range_timestamp_node is not None
    ranged = Timestamp.from_node(range_timestamp_node, document)
    assert ranged.end is not None
    assert ranged.end >= ranged.start
