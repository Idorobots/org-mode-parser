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
    InlineEntity,
    InlineSourceBlock,
    Italic,
    LineBreak,
    Macro,
    PlainLink,
    PlainText,
    RadioTarget,
    RegularLink,
    RichText,
    StrikeThrough,
    Subscript,
    Superscript,
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


def _find_first_node_with_type(root: tree_sitter.Node, target_type: str) -> tree_sitter.Node:
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
    paragraph = _find_first_paragraph_with_prefix(tree.root_node, source, "An inline foot")
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


def test_rich_text_parts_append_marks_dirty() -> None:
    """Appending directly to parts marks rich text dirty."""
    rich_text = RichText("A")

    rich_text.parts.append(PlainText("B"))

    assert rich_text.dirty is True
    assert rich_text.text == "AB"


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
        part for part in rich_text.parts if isinstance(part, PlainText) and str(part) == "\n"
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
            Macro("version"),
            PlainText(" "),
            Macro("date", "%Y-%m-%d"),
            PlainText(" "),
            LineBreak(),
        ]
    )
    expected = (
        "A *bold* /italic/ _under_ +gone+ =raw= ~x()~ [2/5] https://example.org "
        "<https://example.org> [[id:abc][desc]] <<anchor>> <<<radio>>> "
        "<2025-01-01 Wed> [fn:a:d] [cite/t:@k] src_python[:results]{1+1} "
        "@@html:<b>@@ {{{version}}} {{{date(%Y-%m-%d)}}} \\\\"
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


def test_macro_str_no_arguments() -> None:
    """Macro without arguments renders as {{{name}}}."""
    macro = Macro("version")
    assert str(macro) == "{{{version}}}"


def test_macro_str_with_arguments() -> None:
    """Macro with arguments renders as {{{name(args)}}}."""
    macro = Macro("date", "%Y-%m-%d")
    assert str(macro) == "{{{date(%Y-%m-%d)}}}"


def test_macro_from_node_no_arguments(
    example_file: Callable[[str], Path],
) -> None:
    """Macro with no arguments parses name correctly and arguments is None."""
    path = example_file("macro-basic.org")
    source = path.read_bytes()
    tree = load_raw(path)
    document = Document.from_tree(tree, path.name, source)
    macro_node = _find_first_node_with_type(tree.root_node, "macro")

    rt = RichText.from_node(macro_node, document=document)

    assert len(rt.parts) == 1
    macro = rt.parts[0]
    assert isinstance(macro, Macro)
    assert macro.name == "version"
    assert macro.arguments is None


def test_macro_from_node_with_arguments(
    example_file: Callable[[str], Path],
) -> None:
    """Macro with arguments parses name and argument string correctly."""
    path = example_file("macro-basic.org")
    source = path.read_bytes()
    tree = load_raw(path)
    document = Document.from_tree(tree, path.name, source)

    # Find the macro node that carries arguments — it is the second macro in
    # the document (the first one after the heading with {{{date(%Y-%m-%d)}}}).
    macro_nodes: list[tree_sitter.Node] = []
    stack: list[tree_sitter.Node] = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "macro":
            macro_nodes.append(node)
        stack.extend(reversed(node.children))

    args_macro_node = next(n for n in macro_nodes if n.child_by_field_name("arguments") is not None)
    rt = RichText.from_node(args_macro_node, document=document)

    assert len(rt.parts) == 1
    macro = rt.parts[0]
    assert isinstance(macro, Macro)
    assert macro.name == "date"
    assert macro.arguments == "%Y-%m-%d"


def test_macro_parsed_from_loads(tmp_path: Path) -> None:
    """loads() surfaces Macro objects from inline macro call syntax."""
    content = "{{{name}}}\n"
    path = tmp_path / "macro-inline.org"
    path.write_text(content, encoding="utf-8")
    tree = load_raw(path)
    document = loads(content)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)
    macro_parts = [p for p in rich_text.parts if isinstance(p, Macro)]
    assert len(macro_parts) == 1
    assert macro_parts[0].name == "name"
    assert macro_parts[0].arguments is None


# ---------------------------------------------------------------------------
# InlineEntity tests
# ---------------------------------------------------------------------------


def test_entity_named_parsed_from_paragraph(tmp_path: Path) -> None:
    """Named entity \\NAME is parsed as InlineEntity with correct name."""
    content = "\\alpha text\n"
    path = tmp_path / "entity-named.org"
    path.write_text(content, encoding="utf-8")
    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)
    entity_parts = [p for p in rich_text.parts if isinstance(p, InlineEntity)]
    assert len(entity_parts) == 1
    assert entity_parts[0].name == "alpha"
    assert entity_parts[0].has_braces is False


def test_entity_named_with_braces_parsed(tmp_path: Path) -> None:
    """Entity \\NAME{} sets has_braces=True."""
    content = "\\alpha{} text\n"
    path = tmp_path / "entity-braces.org"
    path.write_text(content, encoding="utf-8")
    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)
    entity_parts = [p for p in rich_text.parts if isinstance(p, InlineEntity)]
    assert len(entity_parts) == 1
    assert entity_parts[0].name == "alpha"
    assert entity_parts[0].has_braces is True


def test_entity_nbsp_form_parsed(tmp_path: Path) -> None:
    """Non-breaking-space entity \\_ is parsed as InlineEntity with name='_'."""
    content = "\\_ text\n"
    path = tmp_path / "entity-nbsp.org"
    path.write_text(content, encoding="utf-8")
    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)
    entity_parts = [p for p in rich_text.parts if isinstance(p, InlineEntity)]
    assert len(entity_parts) == 1
    assert entity_parts[0].name == "_"


def test_entity_at_eol_parsed(tmp_path: Path) -> None:
    """Entity at end of line (no post character) is parsed correctly."""
    content = "\\alpha\n"
    path = tmp_path / "entity-eol.org"
    path.write_text(content, encoding="utf-8")
    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)
    entity_parts = [p for p in rich_text.parts if isinstance(p, InlineEntity)]
    assert len(entity_parts) == 1
    assert entity_parts[0].name == "alpha"


def test_entity_backslash_digit_stays_plain_text(tmp_path: Path) -> None:
    """Backslash followed by a digit is not an entity — stays plain text."""
    content = "\\1 not-entity\n"
    path = tmp_path / "entity-digit.org"
    path.write_text(content, encoding="utf-8")
    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)
    entity_parts = [p for p in rich_text.parts if isinstance(p, InlineEntity)]
    assert len(entity_parts) == 0


def test_entity_str_roundtrip_without_braces() -> None:
    """InlineEntity.__str__ renders \\NAME without braces."""
    assert str(InlineEntity(name="alpha")) == "\\alpha"
    assert str(InlineEntity(name="Rightarrow")) == "\\Rightarrow"


def test_entity_str_roundtrip_with_braces() -> None:
    """InlineEntity.__str__ renders \\NAME{} with braces."""
    assert str(InlineEntity(name="alpha", has_braces=True)) == "\\alpha{}"


def test_entity_nbsp_str() -> None:
    """InlineEntity(name='_').__str__ renders the non-breaking-space form."""
    assert str(InlineEntity(name="_")) == "\\_ "


def test_entity_included_in_programmatic_richtext() -> None:
    """InlineEntity instances can be added to RichText programmatically."""
    rt = RichText([InlineEntity(name="alpha"), PlainText(" and "), InlineEntity(name="_")])
    assert "\\alpha" in str(rt)
    assert "\\_ " in str(rt)


def test_subscript_brace_form_parsed(tmp_path: Path) -> None:
    """Subscript brace form parses into Subscript with inline body."""
    content = "x_{i+1}\n"
    path = tmp_path / "subscript-brace.org"
    path.write_text(content, encoding="utf-8")
    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)

    subscript_parts = [p for p in rich_text.parts if isinstance(p, Subscript)]
    assert len(subscript_parts) == 1
    assert subscript_parts[0].form == "{}"
    assert str(subscript_parts[0]) == "_{i+1}"


def test_superscript_paren_form_parsed(tmp_path: Path) -> None:
    """Superscript paren form parses into Superscript with inline body."""
    content = "x^(n-1)\n"
    path = tmp_path / "superscript-paren.org"
    path.write_text(content, encoding="utf-8")
    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)

    superscript_parts = [p for p in rich_text.parts if isinstance(p, Superscript)]
    assert len(superscript_parts) == 1
    assert superscript_parts[0].form == "()"
    assert str(superscript_parts[0]) == "^(n-1)"


def test_script_star_forms_parse(tmp_path: Path) -> None:
    """Star forms ``_*`` and ``^*`` parse as script objects."""
    content = "x_* and y^*\n"
    path = tmp_path / "script-star.org"
    path.write_text(content, encoding="utf-8")
    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)

    assert any(isinstance(part, Subscript) and part.form == "*" for part in rich_text.parts)
    assert any(isinstance(part, Superscript) and part.form == "*" for part in rich_text.parts)


def test_caret_non_script_stays_plain_text(tmp_path: Path) -> None:
    """Caret not followed by script form remains plain text."""
    content = "foo^bar\n"
    path = tmp_path / "script-caret-plain.org"
    path.write_text(content, encoding="utf-8")
    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)

    assert not any(isinstance(part, Superscript) for part in rich_text.parts)
    assert str(rich_text) == content


def test_underscore_word_non_script_stays_plain_text(tmp_path: Path) -> None:
    """Underscore words are not interpreted as subscript."""
    content = "Fixed_Width stays text\n"
    path = tmp_path / "script-underscore-plain.org"
    path.write_text(content, encoding="utf-8")
    document = loads(content)
    tree = load_raw(path)
    paragraph = _find_first_node_with_type(tree.root_node, "paragraph")
    rich_text = RichText.from_node(paragraph, document=document)

    assert not any(isinstance(part, Subscript) for part in rich_text.parts)
    assert str(rich_text) == content
