"""Tests for the semantic Document / Heading / RichText / Element classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser import loads
from org_parser.document import Document, Heading, load_raw
from org_parser.element import (
    Drawer,
    Element,
    Indent,
    Keyword,
    Logbook,
    Paragraph,
    Repeat,
)
from org_parser.text import CompletionCounter, RichText
from org_parser.time import Clock, Timestamp

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_document(path: Path) -> Document:
    """Parse an .org file and build a :class:`Document`."""
    source = path.read_bytes()
    tree = load_raw(path)
    return Document.from_tree(tree, path.name, source)


def _find_kw(doc: Document, key: str) -> Keyword | None:
    """Return the first keyword in *doc.keywords* with *key*, or *None*."""
    return next((kw for kw in doc.keywords if kw.key == key), None)


# ===================================================================
# RichText stub
# ===================================================================


class TestRichText:
    """Tests for the :class:`RichText` stub."""

    def test_str(self) -> None:
        rt = RichText("hello")
        assert str(rt) == "hello"

    def test_repr(self) -> None:
        rt = RichText("hello")
        assert repr(rt) == "RichText('hello')"

    def test_eq_richtext(self) -> None:
        assert RichText("a") == RichText("a")
        assert RichText("a") != RichText("b")

    def test_eq_str(self) -> None:
        assert RichText("hello") == "hello"

    def test_hash(self) -> None:
        assert hash(RichText("x")) == hash(RichText("x"))

    def test_eq_other_type(self) -> None:
        assert RichText("1") != 1


# ===================================================================
# Element stub
# ===================================================================


class TestElement:
    """Tests for the :class:`Element` base class."""

    def test_default_construction(self) -> None:
        e = Element()
        assert isinstance(e, Element)
        assert e.dirty is False
        assert e.parent is None

    def test_repr(self) -> None:
        e = Element()
        assert repr(e) == "Element()"


class TestParagraph:
    """Tests for the :class:`Paragraph` element."""

    def test_construction_with_body(self) -> None:
        paragraph = Paragraph(body=RichText("Hello world.\n"))
        assert isinstance(paragraph, Paragraph)
        assert str(paragraph.body) == "Hello world.\n"

    def test_construction_accepts_raw_string_body(self) -> None:
        """Paragraph constructor accepts raw strings and stores RichText."""
        paragraph = Paragraph(body="Hello world.\n")
        assert isinstance(paragraph.body, RichText)
        assert str(paragraph.body) == "Hello world.\n"

    def test_body_setter_marks_dirty(self) -> None:
        paragraph = Paragraph(body=RichText("Before\n"))
        assert paragraph.dirty is False
        paragraph.body = RichText("After\n")
        assert paragraph.dirty is True
        assert str(paragraph) == "After\n"

    def test_from_tree_recovers_indented_paragraph_indent(self, tmp_path: Path) -> None:
        path = tmp_path / "indented-paragraph.org"
        path.write_text("    continuation\n")
        doc = _load_document(path)

        indent = next((element for element in doc.body if isinstance(element, Indent)), None)

        assert indent is not None
        assert len(indent.body) == 1
        assert isinstance(indent.body[0], Paragraph)


# ===================================================================
# Document — manual construction
# ===================================================================


class TestDocumentManual:
    """Tests for manually constructed :class:`Document` instances."""

    def test_minimum_construction(self) -> None:
        doc = Document(filename="test.org")
        assert doc.filename == "test.org"
        assert doc.title is None
        assert doc.author is None
        # NOTE: No CATEGORY keyword → falls back to filename stem.
        assert doc.category is not None
        assert str(doc.category) == "test"
        assert doc.description is None
        assert doc.todo is None
        assert doc.keywords == []
        assert doc.body == []
        assert doc.children == []

    def test_full_construction(self) -> None:
        doc = Document(
            filename="full.org",
            title=RichText("My Title"),
            author=RichText("An Author"),
            category=RichText("work"),
            description=RichText("A description."),
            todo=RichText("TODO | DONE"),
            keywords=[Keyword(key="LANGUAGE", value=RichText("en"))],
            body=[Paragraph(body=RichText("Hello.\n"))],
        )
        assert doc.title is not None
        assert str(doc.title) == "My Title"
        assert doc.author is not None
        assert str(doc.author) == "An Author"
        assert doc.category is not None
        assert str(doc.category) == "work"
        assert doc.description is not None
        assert str(doc.description) == "A description."
        assert doc.todo is not None
        assert str(doc.todo) == "TODO | DONE"
        lang_kw = _find_kw(doc, "LANGUAGE")
        assert lang_kw is not None
        assert str(lang_kw.value) == "en"
        assert any(kw.key == "TITLE" for kw in doc.keywords)
        assert any(kw.key == "AUTHOR" for kw in doc.keywords)
        assert any(kw.key == "CATEGORY" for kw in doc.keywords)
        assert any(kw.key == "DESCRIPTION" for kw in doc.keywords)
        assert any(kw.key == "TODO" for kw in doc.keywords)
        assert len(doc.body) == 1

    def test_constructor_accepts_raw_string_dedicated_keyword_values(self) -> None:
        """Document constructor accepts raw strings for dedicated keyword values."""
        doc = Document(
            filename="full.org",
            title="My Title",
            author="An Author",
            category="work",
            description="A description.",
            todo="TODO | DONE",
        )
        assert isinstance(doc.title, RichText)
        assert isinstance(doc.author, RichText)
        assert isinstance(doc.category, RichText)
        assert isinstance(doc.description, RichText)
        assert isinstance(doc.todo, RichText)
        assert str(doc.title) == "My Title"
        assert str(doc.author) == "An Author"
        assert str(doc.category) == "work"
        assert str(doc.description) == "A description."
        assert str(doc.todo) == "TODO | DONE"

    def test_repr(self) -> None:
        doc = Document(filename="x.org")
        r = repr(doc)
        assert "Document(" in r
        assert "filename='x.org'" in r
        assert "body=" not in r
        assert "children=" not in r

    def test_dedicated_keyword_getters_use_last_value(self) -> None:
        """Dedicated keyword properties use last-write-wins semantics."""
        doc = Document.from_source("#+TITLE: First\n#+TITLE: Second\n")
        assert doc.title is not None
        assert str(doc.title) == "Second"


# ===================================================================
# Heading — manual construction
# ===================================================================


class TestHeadingManual:
    """Tests for manually constructed :class:`Heading` instances."""

    def test_minimum_construction(self) -> None:
        doc = Document(filename="t.org")
        h = Heading(level=1, document=doc, parent=doc)
        assert h.level == 1
        assert h.parent is doc
        assert h.todo is None
        assert h.is_comment is False
        assert h.priority is None
        assert h.title is None
        assert h.counter is None
        assert h.tags == []
        assert h.scheduled is None
        assert h.deadline is None
        assert h.closed is None
        assert h.body == []
        assert h.children == []

    def test_constructor_accepts_raw_string_title(self) -> None:
        """Heading constructor accepts raw string titles."""
        doc = Document(filename="t.org")
        heading = Heading(level=1, document=doc, parent=doc, title="My heading")
        assert isinstance(heading.title, RichText)
        assert heading.title is not None
        assert str(heading.title) == "My heading"

    def test_document_property_direct_parent(self) -> None:
        doc = Document(filename="t.org")
        h = Heading(level=1, document=doc, parent=doc)
        assert h.document is doc

    def test_document_property_nested(self) -> None:
        doc = Document(filename="t.org")
        h1 = Heading(level=1, document=doc, parent=doc)
        h2 = Heading(level=2, document=doc, parent=h1)
        h3 = Heading(level=3, document=doc, parent=h2)
        assert h3.document is doc

    def test_siblings(self) -> None:
        doc = Document(filename="t.org")
        h1 = Heading(level=1, document=doc, parent=doc)
        h2 = Heading(level=1, document=doc, parent=doc)
        h3 = Heading(level=1, document=doc, parent=doc)
        doc.children.extend([h1, h2, h3])

        sibs = h2.siblings
        assert h1 in sibs
        assert h3 in sibs
        assert h2 not in sibs
        assert len(sibs) == 2

    def test_siblings_empty_when_only_child(self) -> None:
        doc = Document(filename="t.org")
        h = Heading(level=1, document=doc, parent=doc)
        doc.children.append(h)
        assert h.siblings == []

    def test_repr(self) -> None:
        doc = Document(filename="t.org")
        h = Heading(level=2, document=doc, parent=doc, title=RichText("My heading"))
        r = repr(h)
        assert "Heading(" in r
        assert "level=2" in r
        assert "RichText('My heading')" in r
        assert "body=" not in r


# ===================================================================
# Document.from_tree — keyword extraction
# ===================================================================


class TestDocumentFromTreeKeywords:
    """Test keyword extraction via ``Document.from_tree``."""

    def test_special_keywords_basic(self, example_file: Callable[[str], Path]) -> None:
        """Verify TITLE, AUTHOR, CATEGORY from special-keywords-basic.org."""
        doc = _load_document(example_file("special-keywords-basic.org"))

        assert doc.title is not None
        assert isinstance(doc.title, RichText)
        assert str(doc.title) == "Document Title"

        assert doc.author is not None
        assert isinstance(doc.author, RichText)
        assert str(doc.author) == "Qrux Bimble"

        assert doc.category is not None
        assert isinstance(doc.category, RichText)
        assert str(doc.category) == "test"

        title_kw = _find_kw(doc, "TITLE")
        assert title_kw is not None
        assert title_kw.parent is doc
        assert title_kw.value.parent is title_kw
        author_kw = _find_kw(doc, "AUTHOR")
        assert author_kw is not None
        assert author_kw.parent is doc
        assert author_kw.value.parent is author_kw
        category_kw = _find_kw(doc, "CATEGORY")
        assert category_kw is not None
        assert category_kw.parent is doc
        assert category_kw.value.parent is category_kw
        assert any(kw.key == "TITLE" for kw in doc.keywords)
        assert any(kw.key == "AUTHOR" for kw in doc.keywords)
        assert any(kw.key == "CATEGORY" for kw in doc.keywords)

    def test_todo_keyword(self, example_file: Callable[[str], Path]) -> None:
        """The #+TODO keyword is extracted as a dedicated property."""
        doc = _load_document(example_file("special-keywords-basic.org"))
        assert doc.todo is not None
        assert "TODO" in str(doc.todo)
        assert "DONE" in str(doc.todo)

    def test_non_dedicated_keywords_in_dict(self, example_file: Callable[[str], Path]) -> None:
        """Non-dedicated keywords land in the keywords list."""
        doc = _load_document(example_file("special-keywords-basic.org"))
        # DATE and LANGUAGE are not dedicated properties
        assert any(kw.key == "DATE" for kw in doc.keywords)
        assert any(kw.key == "LANGUAGE" for kw in doc.keywords)
        lang_kw = _find_kw(doc, "LANGUAGE")
        assert isinstance(lang_kw, Keyword)
        assert str(lang_kw.value) == "en"

    def test_description_keyword(self, example_file: Callable[[str], Path]) -> None:
        """#+DESCRIPTION is extracted as a dedicated property."""
        doc = _load_document(example_file("zeroth-section.org"))
        assert doc.description is not None
        assert "production tracking" in str(doc.description)

    def test_zeroth_section_body(self, example_file: Callable[[str], Path]) -> None:
        """Non-keyword elements in the zeroth section appear in body."""
        doc = _load_document(example_file("zeroth-section.org"))
        # zeroth-section.org has comments, a property drawer, and a paragraph
        assert len(doc.body) > 0
        assert any(isinstance(e, Paragraph) for e in doc.body)
        assert all(e.parent is doc for e in doc.body)


# ===================================================================
# Document.from_tree — heading structure
# ===================================================================


class TestDocumentFromTreeHeadings:
    """Test heading hierarchy built by ``Document.from_tree``."""

    def test_top_level_headings(self, example_file: Callable[[str], Path]) -> None:
        """nested-headings-basic.org has two top-level headings."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        assert len(doc.children) == 2

    def test_heading_levels(self, example_file: Callable[[str], Path]) -> None:
        """Each heading reports its correct level."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        assert doc.children[0].level == 1
        assert doc.children[1].level == 1

    def test_sub_headings(self, example_file: Callable[[str], Path]) -> None:
        """First heading of nested-headings-basic.org has two sub-headings."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        first = doc.children[0]
        assert len(first.children) == 2
        assert first.children[0].level == 2
        assert first.children[1].level == 2

    def test_deeply_nested(self, example_file: Callable[[str], Path]) -> None:
        """Second sub-heading has a level-3 child."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        second_sub = doc.children[0].children[1]
        assert len(second_sub.children) == 1
        assert second_sub.children[0].level == 3

    def test_parent_references(self, example_file: Callable[[str], Path]) -> None:
        """Parent references point to the correct objects."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        h1 = doc.children[0]
        h2 = h1.children[0]
        h3 = h1.children[1].children[0]

        assert h1.parent is doc
        assert h2.parent is h1
        assert h3.parent is h1.children[1]

    def test_document_property(self, example_file: Callable[[str], Path]) -> None:
        """document property returns the root Document at any depth."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        deep = doc.children[0].children[1].children[0]
        assert deep.document is doc

    def test_siblings(self, example_file: Callable[[str], Path]) -> None:
        """Sibling computation for sub-headings."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        subs = doc.children[0].children
        assert len(subs[0].siblings) == 1
        assert subs[0].siblings[0] is subs[1]


# ===================================================================
# Heading field extraction
# ===================================================================


class TestHeadingFields:
    """Test extraction of individual heading fields from tree-sitter nodes."""

    def test_todo_keyword(self, example_file: Callable[[str], Path]) -> None:
        """TODO keywords are extracted correctly."""
        doc = _load_document(example_file("todo-and-done.org"))
        todos = [h.todo for h in doc.children]
        assert "TODO" in todos
        assert "DONE" in todos
        assert "CANCELLED" in todos

    def test_no_todo_keyword(self, example_file: Callable[[str], Path]) -> None:
        """A heading without a TODO keyword returns None."""
        doc = _load_document(example_file("todo-and-done.org"))
        last = doc.children[-1]
        assert last.todo is None

    def test_priority(self, example_file: Callable[[str], Path]) -> None:
        """Priority values are extracted."""
        doc = _load_document(example_file("priorities-and-special-headings.org"))
        # Find the heading with priority A: "* TODO [#A] Critical: ..."
        priorities = [h.priority for h in doc.children if h.priority is not None]
        assert "A" in priorities
        assert "B" in priorities

    def test_comment_marker(self, example_file: Callable[[str], Path]) -> None:
        """COMMENT heading marker is extracted as a boolean field."""
        doc = _load_document(example_file("priorities-and-special-headings.org"))
        comment_headings = [heading for heading in doc.all_headings if heading.is_comment]
        assert len(comment_headings) > 0
        assert any(heading.title is not None for heading in comment_headings)

    def test_tags(self, example_file: Callable[[str], Path]) -> None:
        """heading_tags are extracted as a list of individual strings."""
        doc = _load_document(example_file("priorities-and-special-headings.org"))
        # * TODO [#A] Critical: ... :ops:critical:
        tagged = [h for h in doc.children if len(h.heading_tags) > 0]
        assert len(tagged) > 0
        # Check that tags are individual strings, not the full `:a:b:` form
        for h in tagged:
            for tag in h.heading_tags:
                assert ":" not in tag

    def test_title_text(self, example_file: Callable[[str], Path]) -> None:
        """Heading title text is preserved verbatim."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        assert doc.children[0].title is not None
        assert str(doc.children[0].title) == "First top-level heading"
        assert doc.children[0].title.parent is doc.children[0]

    def test_heading_body_elements(self, example_file: Callable[[str], Path]) -> None:
        """Heading body contains section elements."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        first = doc.children[0]
        assert len(first.body) > 0
        assert any(isinstance(e, Paragraph) for e in first.body)
        assert all(e.parent is first for e in first.body)

    def test_heading_body_excludes_subheadings(self, example_file: Callable[[str], Path]) -> None:
        """Body elements do not include sub-headings."""
        from org_parser.document import Heading as HeadingType

        doc = _load_document(example_file("nested-headings-basic.org"))
        first = doc.children[0]
        assert not any(isinstance(e, HeadingType) for e in first.body)

    def test_completion_counter(self, tmp_path: Path) -> None:
        """Completion counter inner value is extracted from the title."""
        org = tmp_path / "counter.org"
        org.write_bytes(b"* Tasks [1/3] remaining\n* No counter here\n")
        doc = _load_document(org)
        assert doc.children[0].counter == CompletionCounter("1/3")
        assert doc.children[1].counter is None

    def test_completion_counter_percent(self, tmp_path: Path) -> None:
        """Percentage-style completion counter is extracted."""
        org = tmp_path / "pct.org"
        org.write_bytes(b"* Progress [50%] on feature\n")
        doc = _load_document(org)
        assert doc.children[0].counter == CompletionCounter("50%")

    def test_title_verbatim_with_counter(self, tmp_path: Path) -> None:
        """Title text preserves verbatim source including the counter."""
        org = tmp_path / "title_counter.org"
        org.write_bytes(b"* Tasks [2/5] to finish\n")
        doc = _load_document(org)
        assert doc.children[0].title is not None
        assert str(doc.children[0].title) == "Tasks [2/5] to finish"

    def test_planning_fields(self, example_file: Callable[[str], Path]) -> None:
        """Planning timestamps are extracted into heading planning fields."""
        doc = _load_document(example_file("planning-basic.org"))

        scheduled_heading = doc.children[0]
        deadline_heading = doc.children[1]
        closed_heading = doc.children[2]
        all_three_heading = doc.children[3]

        assert scheduled_heading.scheduled is not None
        assert str(scheduled_heading.scheduled) == "<2025-03-01 Sat>"
        assert scheduled_heading.deadline is None
        assert scheduled_heading.closed is None

        assert deadline_heading.deadline is not None
        assert str(deadline_heading.deadline) == "<2025-04-30 Wed>"
        assert deadline_heading.scheduled is None
        assert deadline_heading.closed is None

        assert closed_heading.closed is not None
        assert str(closed_heading.closed) == "[2025-01-05 Sun 17:00]"
        assert closed_heading.scheduled is None
        assert closed_heading.deadline is None

        assert all_three_heading.scheduled is not None
        assert all_three_heading.deadline is not None
        assert all_three_heading.closed is not None

    def test_malformed_planning_entry_does_not_populate_field(
        self,
        tmp_path: Path,
    ) -> None:
        """Malformed planning entries do not leak partial timestamps."""
        org = tmp_path / "malformed-planning.org"
        org.write_bytes(
            b"* Test\n" b"DEADLINE: [2024-02-02]--<2025-02-02>\n" b"SCHEDULED: <2025-03-01 Sat>\n"
        )

        doc = _load_document(org)
        heading = doc.children[0]

        assert heading.deadline is None
        assert heading.scheduled is not None
        assert str(heading.scheduled) == "<2025-03-01 Sat>"


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge-case scenarios."""

    def test_empty_document(self, tmp_path: Path) -> None:
        """An empty .org file produces a Document with no content."""
        empty = tmp_path / "empty.org"
        empty.write_bytes(b"")
        doc = _load_document(empty)
        assert doc.children == []
        assert doc.body == []
        assert doc.title is None
        assert doc.keywords == []

    def test_heading_levels_file(self, example_file: Callable[[str], Path]) -> None:
        """heading-levels.org has a single chain of nested headings."""
        doc = _load_document(example_file("heading-levels.org"))
        assert len(doc.children) == 1
        h = doc.children[0]
        assert h.level == 1
        # Walk down the chain
        depth = 1
        while h.children:
            h = h.children[0]
            depth += 1
        assert depth == 6
        assert h.level == 6


# ===================================================================
# Document FILETAGS
# ===================================================================


class TestDocumentFiletags:
    """Tests for ``Document.tags`` (``#+FILETAGS:`` parsing and mutation)."""

    def test_tags_parsed_from_file(self, example_file: Callable[[str], Path]) -> None:
        """Document.tags is populated from #+FILETAGS: in the zeroth section."""
        doc = _load_document(example_file("special-keywords-basic.org"))
        assert doc.tags == ["foo", "bar"]

    def test_tags_empty_when_no_filetags(self, tmp_path: Path) -> None:
        """Document.tags returns an empty list when #+FILETAGS: is absent."""
        path = tmp_path / "no-filetags.org"
        path.write_bytes(b"#+TITLE: No Tags\n")
        doc = _load_document(path)
        assert doc.tags == []

    def test_tags_setter_updates_keyword(self) -> None:
        """Setting Document.tags creates or updates the FILETAGS keyword."""
        doc = Document(filename="test.org")
        assert doc.tags == []
        doc.tags = ["alpha", "beta"]
        assert doc.tags == ["alpha", "beta"]
        assert any(kw.key == "FILETAGS" for kw in doc.keywords)
        filetags_kw = _find_kw(doc, "FILETAGS")
        assert filetags_kw is not None
        assert str(filetags_kw.value) == ":alpha:beta:"

    def test_tags_setter_empty_removes_keyword(self) -> None:
        """Setting Document.tags to [] removes the FILETAGS keyword entirely."""
        doc = Document(filename="test.org")
        doc.tags = ["alpha"]
        assert any(kw.key == "FILETAGS" for kw in doc.keywords)
        doc.tags = []
        assert doc.tags == []
        assert not any(kw.key == "FILETAGS" for kw in doc.keywords)

    def test_tags_setter_overwrites_existing(self) -> None:
        """Setting Document.tags twice replaces the previous value."""
        doc = Document(filename="test.org")
        doc.tags = ["old"]
        doc.tags = ["new1", "new2"]
        assert doc.tags == ["new1", "new2"]
        filetags_kw = _find_kw(doc, "FILETAGS")
        assert filetags_kw is not None
        assert str(filetags_kw.value) == ":new1:new2:"

    def test_tags_setter_marks_dirty(self) -> None:
        """Setting Document.tags marks the document dirty."""
        doc = Document(filename="test.org")
        assert not doc.dirty
        doc.tags = ["x"]
        assert doc.dirty

    def test_tags_renders_as_filetags_keyword(self) -> None:
        """A document with tags set renders #+FILETAGS: in its output."""
        doc = Document(filename="test.org")
        doc.tags = ["foo", "bar"]
        rendered = str(doc)
        assert "#+FILETAGS: :foo:bar:" in rendered

    def test_tags_roundtrip(self, tmp_path: Path) -> None:
        """FILETAGS round-trips through parse → set → render correctly."""
        path = tmp_path / "ft.org"
        path.write_bytes(b"#+FILETAGS: :alpha:beta:\n")
        doc = _load_document(path)
        assert doc.tags == ["alpha", "beta"]
        doc.tags = ["gamma", "delta"]
        rendered = str(doc)
        assert "#+FILETAGS: :gamma:delta:" in rendered

    def test_tags_aggregate_multiple_filetags_keywords(self, tmp_path: Path) -> None:
        """Document.tags includes values from all FILETAGS keywords in order."""
        path = tmp_path / "multi-filetags.org"
        path.write_bytes(b"#+FILETAGS: :alpha:beta:\n" b"#+FILETAGS: :gamma:\n")
        doc = _load_document(path)
        assert doc.tags == ["alpha", "beta", "gamma"]

    def test_tags_setter_replaces_all_existing_filetags(self, tmp_path: Path) -> None:
        """Setting Document.tags replaces every existing FILETAGS keyword."""
        path = tmp_path / "replace-filetags.org"
        path.write_bytes(b"#+FILETAGS: :alpha:\n" b"#+FILETAGS: :beta:\n")
        doc = _load_document(path)
        doc.tags = ["new1", "new2"]
        assert doc.tags == ["new1", "new2"]
        assert len([kw for kw in doc.keywords if kw.key == "FILETAGS"]) == 1


# ===================================================================
# Heading inherited tags
# ===================================================================


class TestTagInheritance:
    """Tests for ``Heading.tags`` — inherited tag resolution."""

    def test_root_heading_includes_filetags_and_own(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """Top-level heading tags = FILETAGS + own heading_tags."""
        doc = _load_document(example_file("inherited-tags.org"))
        parent = doc.children[0]  # * Parent Heading :parent_tag:
        assert parent.heading_tags == ["parent_tag"]
        assert parent.tags == ["filetag1", "filetag2", "parent_tag"]

    def test_child_inherits_parent_and_filetags(self, example_file: Callable[[str], Path]) -> None:
        """Child heading tags = FILETAGS + parent's heading_tags + own."""
        doc = _load_document(example_file("inherited-tags.org"))
        child = doc.children[0].children[0]  # ** Child Heading :child_tag:
        assert child.heading_tags == ["child_tag"]
        assert child.tags == ["filetag1", "filetag2", "parent_tag", "child_tag"]

    def test_grandchild_full_chain(self, example_file: Callable[[str], Path]) -> None:
        """Grandchild collects the full FILETAGS → parent → child → own chain."""
        doc = _load_document(example_file("inherited-tags.org"))
        grandchild = doc.children[0].children[0].children[0]
        assert grandchild.heading_tags == ["grandchild_tag"]
        assert grandchild.tags == [
            "filetag1",
            "filetag2",
            "parent_tag",
            "child_tag",
            "grandchild_tag",
        ]

    def test_deduplication_own_tag_matches_ancestor(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """A tag in own heading_tags that already appears in an ancestor is removed."""
        doc = _load_document(example_file("inherited-tags.org"))
        # *** Grandchild With Duplicate Own Tag :parent_tag:
        dup = doc.children[0].children[0].children[1]
        assert dup.heading_tags == ["parent_tag"]
        # parent_tag already came from the grandparent; first occurrence wins.
        assert dup.tags == ["filetag1", "filetag2", "parent_tag", "child_tag"]

    def test_heading_without_own_tags(self, example_file: Callable[[str], Path]) -> None:
        """A heading with no own tags still gets FILETAGS."""
        doc = _load_document(example_file("inherited-tags.org"))
        no_tags = doc.children[1]  # * Heading Without Own Tags
        assert no_tags.heading_tags == []
        assert no_tags.tags == ["filetag1", "filetag2"]

    def test_child_deduplicates_filetag(self, example_file: Callable[[str], Path]) -> None:
        """Own tag that duplicates a FILETAG keeps only the first occurrence."""
        doc = _load_document(example_file("inherited-tags.org"))
        # ** Child With Filetag Duplicate :filetag1:
        child = doc.children[1].children[0]
        assert child.heading_tags == ["filetag1"]
        # filetag1 already came from FILETAGS; deduplicated.
        assert child.tags == ["filetag1", "filetag2"]

    def test_heading_tags_excludes_inherited(self, example_file: Callable[[str], Path]) -> None:
        """heading_tags only contains the tags found on this heading line."""
        doc = _load_document(example_file("inherited-tags.org"))
        child = doc.children[0].children[0]
        # heading_tags must not include parent or FILETAGS
        assert "filetag1" not in child.heading_tags
        assert "filetag2" not in child.heading_tags
        assert "parent_tag" not in child.heading_tags

    def test_tags_readonly(self) -> None:
        """Heading.tags is a read-only property; assignment raises AttributeError."""
        doc = Document(filename="t.org")
        h = Heading(level=1, document=doc, parent=doc)
        try:
            h.tags = ["x"]  # type: ignore[misc]
            assert False, "Expected AttributeError"  # noqa: B011
        except AttributeError:
            pass

    def test_tags_no_filetags_no_ancestors(self) -> None:
        """Heading with no FILETAGS and no ancestor tags: tags == heading_tags."""
        doc = Document(filename="t.org")
        h = Heading(level=1, document=doc, parent=doc, heading_tags=["work", "next"])
        assert h.heading_tags == ["work", "next"]
        assert h.tags == ["work", "next"]

    def test_tags_deduplicate_repeated_own_tags(self) -> None:
        """Repeated tags on one heading line are deduplicated in order."""
        doc = Document(filename="t.org")
        heading = Heading(
            level=1,
            document=doc,
            parent=doc,
            heading_tags=["x", "x", "y", "x"],
        )
        assert heading.tags == ["x", "y"]

    def test_tags_deduplicate_inherited_and_own_repeats(self) -> None:
        """Heading.tags removes duplicates across FILETAGS and own tags."""
        doc = Document.from_source("#+FILETAGS: :x:x:y:\n* H :x:y:z:\n")
        heading = doc.children[0]
        assert heading.tags == ["x", "y", "z"]


# ===================================================================
# Document category — keyword vs filename-stem fallback
# ===================================================================


class TestDocumentCategory:
    """Tests for ``Document.category`` keyword and filename-stem fallback."""

    def test_no_keyword_returns_filename_stem(self) -> None:
        """Without #+CATEGORY:, category is derived from the filename stem."""
        doc = Document(filename="myproject.org")
        assert doc.category is not None
        assert str(doc.category) == "myproject"

    def test_keyword_takes_priority_over_stem(self) -> None:
        """#+CATEGORY: overrides the filename-stem fallback."""
        doc = Document(filename="myproject.org", category=RichText("work"))
        assert doc.category is not None
        assert str(doc.category) == "work"

    def test_empty_filename_returns_none(self) -> None:
        """An empty filename yields no category fallback."""
        doc = Document(filename="")
        assert doc.category is None

    def test_stem_strips_extension_only(self) -> None:
        """Only the final extension is stripped; the rest of the name is kept."""
        doc = Document(filename="my.project.notes.org")
        assert doc.category is not None
        assert str(doc.category) == "my.project.notes"

    def test_nested_path_uses_basename_stem(self) -> None:
        """The stem is computed from the basename, not the full path."""
        doc = Document(filename="a/b/c/report.org")
        assert doc.category is not None
        assert str(doc.category) == "report"

    def test_keyword_removed_exposes_stem_fallback(self) -> None:
        """Removing the #+CATEGORY: keyword re-exposes the filename-stem fallback."""
        doc = Document(filename="tasks.org", category=RichText("work"))
        assert str(doc.category) == "work"
        doc.category = None
        assert doc.category is not None
        assert str(doc.category) == "tasks"

    def test_category_parsed_from_file(self, tmp_path: Path) -> None:
        """#+CATEGORY: in the zeroth section is parsed into Document.category."""
        path = tmp_path / "report.org"
        path.write_bytes(b"#+CATEGORY: quarterly\n")
        doc = _load_document(path)
        assert doc.category is not None
        assert str(doc.category) == "quarterly"

    def test_category_falls_back_to_stem_when_no_keyword(self, tmp_path: Path) -> None:
        """A file without #+CATEGORY: uses its own stem as the category."""
        path = tmp_path / "sprint.org"
        path.write_bytes(b"#+TITLE: Sprint\n")
        doc = _load_document(path)
        assert doc.category is not None
        assert str(doc.category) == "sprint"


# ===================================================================
# Heading.heading_category and Heading.category — inheritance
# ===================================================================


class TestHeadingCategory:
    """Tests for ``Heading.heading_category`` and ``Heading.category``."""

    # -- heading_category (own drawer value) ---------------------------------

    def test_heading_category_none_without_properties(self) -> None:
        """heading_category is None when the heading has no properties drawer."""
        doc = Document(filename="t.org")
        h = Heading(level=1, document=doc, parent=doc)
        assert h.heading_category is None

    def test_heading_category_none_without_category_key(self) -> None:
        """heading_category is None when the drawer exists but lacks CATEGORY."""
        from org_parser.element import Properties

        doc = Document(filename="t.org")
        h = Heading(
            level=1,
            document=doc,
            parent=doc,
            properties=Properties(properties={"ID": RichText("abc")}, parent=None),
        )
        assert h.heading_category is None

    def test_heading_category_returns_drawer_value(self, tmp_path: Path) -> None:
        """heading_category returns the CATEGORY value from the properties drawer."""
        path = tmp_path / "h.org"
        path.write_bytes(b"* My Heading\n:PROPERTIES:\n:CATEGORY: project\n:END:\n")
        doc = _load_document(path)
        h = doc.children[0]
        assert h.heading_category is not None
        assert str(h.heading_category) == "project"

    # -- heading_category setter ---------------------------------------------

    def test_setter_creates_properties_drawer(self) -> None:
        """Setting heading_category populates an initially empty properties drawer."""
        doc = Document(filename="t.org")
        h = Heading(level=1, document=doc, parent=doc)
        assert len(h.properties) == 0
        h.heading_category = RichText("archive")
        assert "CATEGORY" in h.properties
        assert str(h.properties["CATEGORY"]) == "archive"

    def test_setter_updates_existing_drawer(self, tmp_path: Path) -> None:
        """Setting heading_category updates an existing properties drawer."""
        path = tmp_path / "h.org"
        path.write_bytes(b"* My Heading\n:PROPERTIES:\n:CATEGORY: old\n:END:\n")
        doc = _load_document(path)
        h = doc.children[0]
        h.heading_category = RichText("new")
        assert str(h.heading_category) == "new"

    def test_setter_none_removes_category_key(self, tmp_path: Path) -> None:
        """Setting heading_category to None removes the CATEGORY key."""
        path = tmp_path / "h.org"
        path.write_bytes(b"* My Heading\n:PROPERTIES:\n:CATEGORY: project\n:END:\n")
        doc = _load_document(path)
        h = doc.children[0]
        assert h.heading_category is not None
        h.heading_category = None
        assert h.heading_category is None
        assert "CATEGORY" not in h.properties

    def test_setter_none_noop_when_key_absent(self) -> None:
        """Setting heading_category to None is a no-op when key is already absent."""
        doc = Document(filename="t.org")
        h = Heading(level=1, document=doc, parent=doc)
        h.heading_category = None  # must not raise, must not mark dirty
        assert h.dirty is False
        assert doc.dirty is False

    def test_setter_marks_dirty(self) -> None:
        """Setting heading_category marks the heading and document dirty."""
        doc = Document(filename="t.org")
        h = Heading(level=1, document=doc, parent=doc)
        assert h.dirty is False
        assert doc.dirty is False
        h.heading_category = RichText("sprint")
        assert h.dirty is True
        assert doc.dirty is True

    def test_setter_none_existing_marks_dirty(self, tmp_path: Path) -> None:
        """Removing an existing CATEGORY key marks the heading and document dirty."""
        path = tmp_path / "h.org"
        path.write_bytes(b"* My Heading\n:PROPERTIES:\n:CATEGORY: x\n:END:\n")
        doc = _load_document(path)
        h = doc.children[0]
        assert h.dirty is False
        assert doc.dirty is False
        h.heading_category = None
        assert h.dirty is True
        assert doc.dirty is True

    # -- category (read-only, inherited) -------------------------------------

    def test_category_returns_own_when_set(self, tmp_path: Path) -> None:
        """category returns the heading's own CATEGORY when present."""
        path = tmp_path / "h.org"
        path.write_bytes(b"* My Heading\n:PROPERTIES:\n:CATEGORY: mine\n:END:\n")
        doc = _load_document(path)
        h = doc.children[0]
        assert h.category is not None
        assert str(h.category) == "mine"

    def test_category_inherits_from_document(self) -> None:
        """Top-level heading with no drawer inherits the document category."""
        doc = Document(filename="tasks.org", category=RichText("work"))
        h = Heading(level=1, document=doc, parent=doc)
        assert h.heading_category is None
        assert h.category is not None
        assert str(h.category) == "work"

    def test_category_inherits_document_filename_stem(self) -> None:
        """Heading inherits the document's filename-stem category when no keyword."""
        doc = Document(filename="journal.org")
        h = Heading(level=1, document=doc, parent=doc)
        assert h.category is not None
        assert str(h.category) == "journal"

    def test_category_inherits_from_parent_heading(self, tmp_path: Path) -> None:
        """Child heading inherits CATEGORY from its parent heading's drawer."""
        path = tmp_path / "h.org"
        path.write_bytes(b"* Parent\n:PROPERTIES:\n:CATEGORY: parent-cat\n:END:\n** Child\n")
        doc = _load_document(path)
        parent = doc.children[0]
        child = parent.children[0]
        assert child.heading_category is None
        assert child.category is not None
        assert str(child.category) == "parent-cat"

    def test_category_own_overrides_parent(self, tmp_path: Path) -> None:
        """Child with own CATEGORY overrides the parent's value."""
        path = tmp_path / "h.org"
        path.write_bytes(
            b"* Parent\n:PROPERTIES:\n:CATEGORY: parent-cat\n:END:\n"
            b"** Child\n:PROPERTIES:\n:CATEGORY: child-cat\n:END:\n"
        )
        doc = _load_document(path)
        parent = doc.children[0]
        child = parent.children[0]
        assert str(parent.category) == "parent-cat"
        assert str(child.category) == "child-cat"

    def test_category_full_chain(self, tmp_path: Path) -> None:
        """Full chain: grandchild inherits through parent to document."""
        path = tmp_path / "h.org"
        path.write_bytes(b"#+CATEGORY: doc-cat\n" b"* Parent\n" b"** Child\n" b"*** Grandchild\n")
        doc = _load_document(path)
        parent = doc.children[0]
        child = parent.children[0]
        grandchild = child.children[0]
        assert str(doc.category) == "doc-cat"
        assert str(parent.category) == "doc-cat"
        assert str(child.category) == "doc-cat"
        assert str(grandchild.category) == "doc-cat"

    def test_category_is_readonly(self) -> None:
        """Heading.category is read-only; assignment raises AttributeError."""
        doc = Document(filename="t.org")
        h = Heading(level=1, document=doc, parent=doc)
        try:
            h.category = RichText("x")  # type: ignore[misc]
            assert False, "Expected AttributeError"  # noqa: B011
        except AttributeError:
            pass


# ===================================================================
# Convenience fields
# ===================================================================


class TestDocumentConvenienceFields:
    """Tests for convenience read-only fields on :class:`Document`."""

    def test_is_root_is_always_true(self) -> None:
        """Document.is_root always reports True."""
        assert Document(filename="x.org").is_root is True

    def test_is_leaf_depends_on_children(self) -> None:
        """Document.is_leaf reflects whether top-level headings exist."""
        doc = Document(filename="x.org")
        assert doc.is_leaf is True
        doc.children = [Heading(level=1, document=doc, parent=doc)]
        assert doc.is_leaf is False

    def test_todo_state_groups_from_todo_keyword(self, example_file: Callable[[str], Path]) -> None:
        """TODO state convenience lists are parsed from #+TODO:."""
        doc = _load_document(example_file("todo-and-done.org"))
        assert doc.todo_states == ["TODO", "IN-PROGRESS", "WAITING"]
        assert doc.done_states == ["DONE", "CANCELLED"]
        assert doc.all_states == [
            "TODO",
            "IN-PROGRESS",
            "WAITING",
            "DONE",
            "CANCELLED",
        ]

    def test_todo_state_groups_without_todo_keyword(self) -> None:
        """Missing #+TODO: yields empty state groups."""
        doc = Document(filename="x.org")
        assert doc.todo_states == []
        assert doc.done_states == []
        assert doc.all_states == []

    def test_todo_state_groups_strip_fast_selection_metadata(self) -> None:
        """TODO states ignore fast-selection metadata in parentheses."""
        doc = Document(filename="x.org", todo=RichText("TODO(t) | DONE(d@/!)"))
        assert doc.todo_states == ["TODO"]
        assert doc.done_states == ["DONE"]
        assert doc.all_states == ["TODO", "DONE"]

    def test_todo_state_groups_support_done_only_definition(self) -> None:
        """TODO definitions can declare only done states after ``|``."""
        doc = Document(filename="x.org", todo=RichText("| CANCELLED(c@/!) REWORKED(r@/!)"))
        assert doc.todo_states == []
        assert doc.done_states == ["CANCELLED", "REWORKED"]
        assert doc.all_states == ["CANCELLED", "REWORKED"]

    def test_todo_state_groups_across_multiple_todo_keywords(self, tmp_path: Path) -> None:
        """State groups aggregate across multiple ``#+TODO:`` keywords."""
        path = tmp_path / "multi-todo.org"
        path.write_bytes(
            b"#+TODO: TODO(t) IN-PROGRESS(i) | DONE(d@/!)\n"
            b"#+TODO: | CANCELLED(c@/!) REWORKED(r@/!)\n"
            b"* TODO Sample task\n"
        )
        doc = _load_document(path)
        assert doc.todo_states == ["TODO", "IN-PROGRESS"]
        assert doc.done_states == ["DONE", "CANCELLED", "REWORKED"]
        assert doc.all_states == [
            "TODO",
            "IN-PROGRESS",
            "DONE",
            "CANCELLED",
            "REWORKED",
        ]

    def test_body_text_joins_zeroth_section_elements(self) -> None:
        """body_text concatenates the string output of body elements."""
        doc = Document(
            filename="x.org",
            body=[
                Paragraph(body=RichText("alpha\n")),
                Paragraph(body=RichText("beta\n")),
            ],
        )
        assert doc.body_text == "alpha\nbeta\n"

    def test_all_headings_returns_flat_file_order(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """all_headings flattens the heading tree in definition order."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        assert [heading.title_text for heading in doc.all_headings] == [
            "First top-level heading",
            "First sub-heading",
            "Second sub-heading",
            "Deeply nested heading",
            "Second top-level heading",
        ]


class TestHeadingConvenienceFields:
    """Tests for convenience read-only fields on :class:`Heading`."""

    def test_is_root_is_always_false(self) -> None:
        """Heading.is_root is always False, including top-level headings."""
        doc = Document(filename="x.org")
        top = Heading(level=1, document=doc, parent=doc)
        nested = Heading(level=2, document=doc, parent=top)
        assert top.is_root is False
        assert nested.is_root is False

    def test_is_leaf_depends_on_children(self) -> None:
        """Heading.is_leaf reflects whether child headings exist."""
        doc = Document(filename="x.org")
        parent = Heading(level=1, document=doc, parent=doc)
        child = Heading(level=2, document=doc, parent=parent)
        assert parent.is_leaf is True
        parent.children = [child]
        assert parent.is_leaf is False

    def test_line_and_column_without_parse_node(self) -> None:
        """line/column are None for programmatically created headings."""
        doc = Document(filename="x.org")
        heading = Heading(level=1, document=doc, parent=doc)

        assert heading.line is None
        assert heading.column is None

    def test_line_and_column_delegate_to_parse_node(self) -> None:
        """line/column mirror the underlying tree-sitter start point."""
        document = loads("Intro\n\n* H\n")
        heading = document.children[0]

        assert heading.line == 2
        assert heading.column == 0

    def test_is_completed_uses_document_done_states(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """is_completed checks heading todo state against document done states."""
        doc = _load_document(example_file("todo-and-done.org"))
        done = next(heading for heading in doc.children if heading.todo == "DONE")
        todo = next(heading for heading in doc.children if heading.todo == "TODO")
        assert done.is_completed is True
        assert todo.is_completed is False

    def test_is_completed_false_for_state_not_in_done_states(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """A TODO value not listed in done states is not considered complete."""
        doc = _load_document(example_file("todo_keys.org"))
        assert doc.children[0].todo == "DONE"
        assert doc.done_states == ["CANCELLED"]
        assert doc.children[0].is_completed is False

    def test_timestamp_aggregation_and_extrema(self) -> None:
        """Heading timestamp helpers include planning, repeat, and clock values."""
        doc = Document(filename="x.org", todo=RichText("TODO | DONE"))
        scheduled = Timestamp(is_active=True, start_year=2025, start_month=1, start_day=2)
        closed = Timestamp(is_active=False, start_year=2025, start_month=1, start_day=9)
        deadline = Timestamp(is_active=True, start_year=2025, start_month=1, start_day=7)
        repeat_timestamp = Timestamp(
            is_active=False,
            start_year=2025,
            start_month=1,
            start_day=5,
        )
        clock_timestamp = Timestamp(
            is_active=False,
            start_year=2025,
            start_month=1,
            start_day=3,
            start_hour=10,
            start_minute=0,
            end_year=2025,
            end_month=1,
            end_day=3,
            end_hour=11,
            end_minute=0,
        )
        heading = Heading(
            level=1,
            document=doc,
            parent=doc,
            scheduled=scheduled,
            closed=closed,
            deadline=deadline,
            logbook=Logbook(
                repeats=[Repeat(after="DONE", before="TODO", timestamp=repeat_timestamp)],
                clock_entries=[Clock(timestamp=clock_timestamp)],
            ),
        )

        assert heading.has_timestamp is True
        assert heading.timestamps == [
            scheduled,
            closed,
            deadline,
            repeat_timestamp,
            clock_timestamp,
        ]
        assert heading.earliest_timestamp is scheduled
        assert heading.latest_timestamp is closed

    def test_timestamp_helpers_when_empty(self) -> None:
        """Timestamp convenience fields are empty/None without timestamp data."""
        doc = Document(filename="x.org")
        heading = Heading(level=1, document=doc, parent=doc)
        assert heading.has_timestamp is False
        assert heading.timestamps == []
        assert heading.earliest_timestamp is None
        assert heading.latest_timestamp is None

    def test_latest_timestamp_prefers_end_when_present(self) -> None:
        """latest_timestamp compares by end datetime when a range has one."""
        doc = Document(filename="x.org")
        with_end = Timestamp(
            is_active=False,
            start_year=2025,
            start_month=1,
            start_day=1,
            start_hour=23,
            start_minute=0,
            end_year=2025,
            end_month=1,
            end_day=10,
            end_hour=1,
            end_minute=0,
        )
        later_start_only = Timestamp(
            is_active=True,
            start_year=2025,
            start_month=1,
            start_day=9,
        )
        heading = Heading(
            level=1,
            document=doc,
            parent=doc,
            scheduled=later_start_only,
            logbook=Logbook(clock_entries=[Clock(timestamp=with_end)]),
        )

        assert heading.latest_timestamp is with_end

    def test_title_body_and_heading_text_fields(self) -> None:
        """title_text, body_text, and heading_text return stringified content."""
        doc = Document(filename="x.org")
        heading = Heading(
            level=1,
            document=doc,
            parent=doc,
            todo="TODO",
            priority="A",
            title=RichText("Feature work"),
            heading_tags=["project", "urgent"],
            body=[Paragraph(body=RichText("Body line\n"))],
        )
        assert heading.title_text == "Feature work"
        assert heading.body_text == "Body line\n"
        assert heading.heading_text == "* TODO [#A] Feature work :project:urgent:"


class TestElementConvenienceFields:
    """Tests for convenience read-only fields on :class:`Element` subclasses."""

    def test_text_returns_stringified_element(self) -> None:
        """Element.text matches __str__ output."""
        paragraph = Paragraph(body=RichText("hello\n"))
        assert paragraph.text == "hello\n"

    def test_line_and_column_without_parse_node(self) -> None:
        """line/column are None for elements without parse backing."""
        element = Element()

        assert element.line is None
        assert element.column is None

    def test_line_and_column_delegate_to_parse_node(self) -> None:
        """line/column mirror parse-backed element start points."""
        document = loads("  indented\n")

        assert isinstance(document.body[0], Indent)
        indent = document.body[0]
        assert indent.line == 0
        assert indent.column == 0
        assert isinstance(indent.body[0], Paragraph)
        paragraph = indent.body[0]
        assert paragraph.line == 0
        assert paragraph.column == 2

    def test_body_text_for_rich_text_body(self) -> None:
        """Element.body_text returns text for scalar body values."""
        paragraph = Paragraph(body=RichText("hello\n"))
        assert paragraph.body_text == "hello\n"

    def test_body_text_for_list_body(self) -> None:
        """Element.body_text joins text for list-style body attributes."""
        drawer = Drawer(
            name="NOTES",
            body=[
                Paragraph(body=RichText("one\n")),
                Paragraph(body=RichText("two\n")),
            ],
        )
        assert drawer.body_text == "one\ntwo\n"

    def test_indent_body_setter_accepts_element_and_raw_string(self) -> None:
        """Indent body setter accepts one element and raw string input."""
        indent = Indent(indent="  ")
        paragraph = Paragraph(body=RichText("line\n"))

        indent.body = paragraph

        assert indent.body == [paragraph]
        assert indent.body[0].parent is indent

        indent.body = "next line"

        assert len(indent.body) == 1
        assert isinstance(indent.body[0], Paragraph)
        assert str(indent.body[0]) == "next line"
        assert indent.body[0].parent is indent
        assert str(indent) == "next line\n"

    def test_indent_body_append_marks_dirty(self) -> None:
        """Appending to indent body marks the indent dirty."""
        indent = Indent(indent="  ")
        paragraph = Paragraph(body=RichText("line\n"))

        indent.body.append(paragraph)

        assert indent.dirty is True
        assert paragraph.parent is indent

    def test_body_text_empty_when_body_missing(self) -> None:
        """Element.body_text is empty when no body attribute exists."""
        assert Element().body_text == ""
