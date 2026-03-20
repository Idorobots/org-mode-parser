"""Tests for the semantic Document / Heading / RichText / Element classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.document import Document, Heading, load_raw
from org_parser.element import Element, Keyword, Paragraph
from org_parser.text import CompletionCounter, RichText

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
        assert paragraph.indent is None

    def test_construction_with_indent(self) -> None:
        paragraph = Paragraph(body=RichText("Hello world.\n"), indent="  ")
        assert paragraph.indent == "  "

    def test_body_setter_marks_dirty(self) -> None:
        paragraph = Paragraph(body=RichText("Before\n"))
        assert paragraph.dirty is False
        paragraph.body = RichText("After\n")
        assert paragraph.dirty is True
        assert str(paragraph) == "After\n"

    def test_indent_setter_marks_dirty(self) -> None:
        paragraph = Paragraph(body=RichText("Before\n"))
        assert paragraph.dirty is False
        paragraph.indent = "    "
        assert paragraph.dirty is True
        assert paragraph.indent == "    "

    def test_from_tree_recovers_indented_paragraph_indent(self, tmp_path: Path) -> None:
        path = tmp_path / "indented-paragraph.org"
        path.write_text("    continuation\n")
        doc = _load_document(path)

        paragraph = next(
            (element for element in doc.body if isinstance(element, Paragraph)),
            None,
        )

        assert paragraph is not None
        assert paragraph.indent is None


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
        assert doc.category is None
        assert doc.description is None
        assert doc.todo is None
        assert doc.keywords == {}
        assert doc.body == []
        assert doc.children == []

    def test_full_construction(self) -> None:
        doc = Document(
            filename="full.org",
            title=Keyword(key="TITLE", value=RichText("My Title")),
            author=Keyword(key="AUTHOR", value=RichText("An Author")),
            category=Keyword(key="CATEGORY", value=RichText("work")),
            description=Keyword(key="DESCRIPTION", value=RichText("A description.")),
            todo=Keyword(key="TODO", value=RichText("TODO | DONE")),
            keywords={"LANGUAGE": Keyword(key="LANGUAGE", value=RichText("en"))},
            body=[Paragraph(body=RichText("Hello.\n"))],
        )
        assert doc.title is not None
        assert str(doc.title.value) == "My Title"
        assert doc.author is not None
        assert str(doc.author.value) == "An Author"
        assert doc.category is not None
        assert str(doc.category.value) == "work"
        assert doc.description is not None
        assert str(doc.description.value) == "A description."
        assert doc.todo is not None
        assert str(doc.todo.value) == "TODO | DONE"
        assert str(doc.keywords["LANGUAGE"].value) == "en"
        assert "TITLE" in doc.keywords
        assert "AUTHOR" in doc.keywords
        assert "CATEGORY" in doc.keywords
        assert "DESCRIPTION" in doc.keywords
        assert "TODO" in doc.keywords
        assert len(doc.body) == 1

    def test_repr(self) -> None:
        doc = Document(filename="x.org")
        r = repr(doc)
        assert "Document(" in r
        assert "filename='x.org'" in r
        assert "body=" not in r
        assert "children=" not in r


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
        assert h.priority is None
        assert h.title is None
        assert h.counter is None
        assert h.tags == []
        assert h.scheduled is None
        assert h.deadline is None
        assert h.closed is None
        assert h.body == []
        assert h.children == []

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
        assert isinstance(doc.title, Keyword)
        assert str(doc.title.value) == "Document Title"

        assert doc.author is not None
        assert isinstance(doc.author, Keyword)
        assert str(doc.author.value) == "Qrux Bimble"

        assert doc.category is not None
        assert isinstance(doc.category, Keyword)
        assert str(doc.category.value) == "test"
        assert doc.title.parent is doc
        assert doc.title.value.parent is doc.title
        assert doc.author.parent is doc
        assert doc.author.value.parent is doc.author
        assert doc.category.parent is doc
        assert doc.category.value.parent is doc.category
        assert "TITLE" in doc.keywords
        assert "AUTHOR" in doc.keywords
        assert "CATEGORY" in doc.keywords

    def test_todo_keyword(self, example_file: Callable[[str], Path]) -> None:
        """The #+TODO keyword is extracted as a dedicated property."""
        doc = _load_document(example_file("special-keywords-basic.org"))
        assert doc.todo is not None
        assert "TODO" in str(doc.todo.value)
        assert "DONE" in str(doc.todo.value)

    def test_non_dedicated_keywords_in_dict(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """Non-dedicated keywords land in the keywords dict."""
        doc = _load_document(example_file("special-keywords-basic.org"))
        # DATE and LANGUAGE are not dedicated properties
        assert "DATE" in doc.keywords
        assert "LANGUAGE" in doc.keywords
        assert isinstance(doc.keywords["LANGUAGE"], Keyword)
        assert str(doc.keywords["LANGUAGE"].value) == "en"

    def test_description_keyword(self, example_file: Callable[[str], Path]) -> None:
        """#+DESCRIPTION is extracted as a dedicated property."""
        doc = _load_document(example_file("zeroth-section.org"))
        assert doc.description is not None
        assert "production tracking" in str(doc.description.value)

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

    def test_tags(self, example_file: Callable[[str], Path]) -> None:
        """Tags are extracted as a list of strings."""
        doc = _load_document(example_file("priorities-and-special-headings.org"))
        # "* TODO [#A] Critical: ... :ops:critical:"
        tagged = [h for h in doc.children if len(h.tags) > 0]
        assert len(tagged) > 0
        # Check that tags are individual strings, not the full `:a:b:` form
        for h in tagged:
            for tag in h.tags:
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

    def test_heading_body_excludes_subheadings(
        self, example_file: Callable[[str], Path]
    ) -> None:
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
        assert doc.keywords == {}

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
