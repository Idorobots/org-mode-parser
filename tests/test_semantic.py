"""Tests for the semantic Document / Heading / RichText / Element classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.document import Document, Heading, load_raw
from org_parser.element import Element
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
    """Tests for the :class:`Element` stub."""

    def test_default_construction(self) -> None:
        e = Element()
        assert e.node_type == ""
        assert e.source_text == ""

    def test_construction_with_values(self) -> None:
        e = Element(node_type="paragraph", source_text="Hello world.")
        assert e.node_type == "paragraph"
        assert e.source_text == "Hello world."

    def test_repr(self) -> None:
        e = Element(node_type="paragraph", source_text="short")
        r = repr(e)
        assert "paragraph" in r
        assert "short" in r


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
            title=RichText("My Title"),
            author=RichText("An Author"),
            category=RichText("work"),
            description=RichText("A description."),
            todo=RichText("TODO | DONE"),
            keywords={"LANGUAGE": RichText("en")},
            body=[Element(node_type="paragraph", source_text="Hello.")],
        )
        assert doc.title == "My Title"
        assert doc.author == "An Author"
        assert doc.category == "work"
        assert doc.description == "A description."
        assert doc.todo == "TODO | DONE"
        assert doc.keywords["LANGUAGE"] == "en"
        assert len(doc.body) == 1

    def test_repr(self) -> None:
        doc = Document(filename="x.org")
        r = repr(doc)
        assert "x.org" in r


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
        assert "**" in r
        assert "My heading" in r


# ===================================================================
# Document.from_tree — keyword extraction
# ===================================================================


class TestDocumentFromTreeKeywords:
    """Test keyword extraction via ``Document.from_tree``."""

    def test_special_keywords_basic(self, example_file: Callable[[str], Path]) -> None:
        """Verify TITLE, AUTHOR, CATEGORY from special-keywords-basic.org."""
        doc = _load_document(example_file("special-keywords-basic.org"))

        assert doc.title is not None
        assert str(doc.title) == "Document Title"

        assert doc.author is not None
        assert str(doc.author) == "Qrux Bimble"

        assert doc.category is not None
        assert str(doc.category) == "test"

    def test_todo_keyword(self, example_file: Callable[[str], Path]) -> None:
        """The #+TODO keyword is extracted as a dedicated property."""
        doc = _load_document(example_file("special-keywords-basic.org"))
        assert doc.todo is not None
        assert "TODO" in str(doc.todo)
        assert "DONE" in str(doc.todo)

    def test_non_dedicated_keywords_in_dict(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """Non-dedicated keywords land in the keywords dict."""
        doc = _load_document(example_file("special-keywords-basic.org"))
        # DATE and LANGUAGE are not dedicated properties
        assert "DATE" in doc.keywords
        assert "LANGUAGE" in doc.keywords
        assert str(doc.keywords["LANGUAGE"]) == "en"

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
        node_types = [e.node_type for e in doc.body]
        assert "paragraph" in node_types


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

    def test_heading_body_elements(self, example_file: Callable[[str], Path]) -> None:
        """Heading body contains section elements."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        first = doc.children[0]
        assert len(first.body) > 0
        assert any(e.node_type == "paragraph" for e in first.body)

    def test_heading_body_excludes_subheadings(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """Body elements do not include sub-headings."""
        doc = _load_document(example_file("nested-headings-basic.org"))
        first = doc.children[0]
        assert all(e.node_type != "heading" for e in first.body)

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
