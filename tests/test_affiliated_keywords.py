"""Tests for affiliated keyword attachment to following elements."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser import loads
from org_parser.element import (
    AffiliatedKeyword,
    BlankLine,
    CaptionKeyword,
    Element,
    List,
    Paragraph,
    PlotKeyword,
    ResultsKeyword,
    SourceBlock,
    Table,
    TblnameKeyword,
)
from org_parser.text import RichText

if TYPE_CHECKING:
    from collections.abc import Sequence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _non_blank(elements: Sequence[Element]) -> list[Element]:
    """Return body elements excluding blank-line separators."""
    return [e for e in elements if not isinstance(e, BlankLine)]


# ---------------------------------------------------------------------------
# Element.keywords default and attach_keyword API
# ---------------------------------------------------------------------------


class TestAttachKeywordAPI:
    """Unit tests for the Element.keywords property and attach_keyword method."""

    def test_keywords_default_empty(self) -> None:
        """A fresh element has an empty keywords list, never None."""
        para = Paragraph(body=RichText("hello\n"))
        assert para.keywords == []

    def test_attach_keyword_does_not_dirty(self) -> None:
        """attach_keyword must not flip the dirty flag."""
        para = Paragraph(body=RichText("hello\n"))
        kw = CaptionKeyword(value="desc")
        assert not para.dirty
        para.attach_keyword(kw)
        assert not para.dirty

    def test_attach_keyword_appends_in_order(self) -> None:
        """Multiple attach_keyword calls accumulate in call order."""
        para = Paragraph(body=RichText("hello\n"))
        kw1 = TblnameKeyword(value="t1")
        kw2 = CaptionKeyword(value="cap")
        para.attach_keyword(kw1)
        para.attach_keyword(kw2)
        assert para.keywords == [kw1, kw2]

    def test_attach_keyword_is_void(self) -> None:
        """attach_keyword has no return value — it does not return a dirty marker."""
        para = Paragraph(body=RichText("hello\n"))
        # Calling without assignment; method is void by design.
        para.attach_keyword(CaptionKeyword(value="x"))
        assert len(para.keywords) == 1

    def test_keywords_list_is_independent_across_instances(self) -> None:
        """Each element instance has its own keywords list."""
        p1 = Paragraph(body=RichText("a\n"))
        p2 = Paragraph(body=RichText("b\n"))
        p1.attach_keyword(CaptionKeyword(value="for p1"))
        assert p2.keywords == []


# ---------------------------------------------------------------------------
# AffiliatedKeyword public export
# ---------------------------------------------------------------------------


class TestAffiliatedKeywordExport:
    """AffiliatedKeyword is publicly importable and is the correct base."""

    def test_imported_from_element_package(self) -> None:
        """AffiliatedKeyword can be imported directly from org_parser.element."""
        from org_parser.element import AffiliatedKeyword as Base

        assert Base is AffiliatedKeyword

    def test_caption_is_subclass(self) -> None:
        """CaptionKeyword is a subclass of AffiliatedKeyword."""
        assert issubclass(CaptionKeyword, AffiliatedKeyword)

    def test_tblname_is_subclass(self) -> None:
        """TblnameKeyword is a subclass of AffiliatedKeyword."""
        assert issubclass(TblnameKeyword, AffiliatedKeyword)

    def test_plot_is_subclass(self) -> None:
        """PlotKeyword is a subclass of AffiliatedKeyword."""
        assert issubclass(PlotKeyword, AffiliatedKeyword)

    def test_results_is_subclass(self) -> None:
        """ResultsKeyword is a subclass of AffiliatedKeyword."""
        assert issubclass(ResultsKeyword, AffiliatedKeyword)


# ---------------------------------------------------------------------------
# Parsing — keyword attachment in document body
# ---------------------------------------------------------------------------


class TestAttachmentInDocumentBody:
    """Affiliated keywords are attached to the following element after parsing."""

    def test_caption_attached_to_table(self) -> None:
        """#+CAPTION before a table is attached to that table's keywords."""
        doc = loads("#+CAPTION: my caption\n| a | b |\n| c | d |\n")
        body = _non_blank(doc.body)
        assert len(body) == 2  # CaptionKeyword, Table
        table = body[1]
        assert isinstance(table, Table)
        assert len(table.keywords) == 1
        kw = table.keywords[0]
        assert isinstance(kw, CaptionKeyword)
        assert kw.value == "my caption"

    def test_tblname_attached_to_table(self) -> None:
        """#+TBLNAME before a table is attached to that table's keywords."""
        doc = loads("#+TBLNAME: mytable\n| x | y |\n")
        body = _non_blank(doc.body)
        table = body[1]
        assert isinstance(table, Table)
        assert len(table.keywords) == 1
        assert isinstance(table.keywords[0], TblnameKeyword)
        assert table.keywords[0].value == "mytable"

    def test_results_attached_to_src_block(self) -> None:
        """#+RESULTS before a source block is attached to that block."""
        doc = loads("#+RESULTS:\n" "#+begin_src python\n" "print('hi')\n" "#+end_src\n")
        body = _non_blank(doc.body)
        block = body[1]
        assert isinstance(block, SourceBlock)
        assert len(block.keywords) == 1
        assert isinstance(block.keywords[0], ResultsKeyword)

    def test_plot_attached_to_table(self) -> None:
        """#+PLOT before a table is attached to that table's keywords."""
        doc = loads('#+PLOT: title:"Sales"\n| q | v |\n')
        body = _non_blank(doc.body)
        table = body[1]
        assert isinstance(table, Table)
        assert len(table.keywords) == 1
        assert isinstance(table.keywords[0], PlotKeyword)

    def test_multiple_keywords_before_one_element(self) -> None:
        """Several consecutive affiliated keywords all attach to the next element."""
        doc = loads(
            "#+TBLNAME: sales\n"
            "#+CAPTION: Quarterly results\n"
            "#+PLOT: title:Sales\n"
            "| q | v |\n"
        )
        body = _non_blank(doc.body)
        table = body[3]
        assert isinstance(table, Table)
        assert len(table.keywords) == 3
        assert isinstance(table.keywords[0], TblnameKeyword)
        assert isinstance(table.keywords[1], CaptionKeyword)
        assert isinstance(table.keywords[2], PlotKeyword)

    def test_trailing_keyword_without_following_element(self) -> None:
        """A trailing affiliated keyword with no following element is skipped."""
        doc = loads("Some paragraph.\n\n#+CAPTION: orphan\n")
        # No exception; caption keyword is a body element but attached to nothing.
        body = _non_blank(doc.body)
        caption_kws = [e for e in body if isinstance(e, CaptionKeyword)]
        assert len(caption_kws) == 1
        # The paragraph does not receive this keyword.
        paragraphs = [e for e in body if isinstance(e, Paragraph)]
        assert paragraphs[0].keywords == []

    def test_unrelated_element_receives_no_keywords(self) -> None:
        """Elements not immediately preceded by affiliated keywords are empty."""
        doc = loads("Plain paragraph.\n\n| a | b |\n")
        body = _non_blank(doc.body)
        para = body[0]
        assert isinstance(para, Paragraph)
        assert para.keywords == []
        table = body[1]
        assert isinstance(table, Table)
        assert table.keywords == []

    def test_keywords_remain_in_body(self) -> None:
        """Affiliated keywords are not removed from the body list after attachment."""
        doc = loads("#+CAPTION: keep me\n| a | b |\n")
        body = _non_blank(doc.body)
        caption_kws = [e for e in body if isinstance(e, CaptionKeyword)]
        assert len(caption_kws) == 1

    def test_keyword_does_not_appear_in_element_str(self) -> None:
        """str(table) does not include the affiliated keyword text."""
        doc = loads("#+CAPTION: invisible\n| a | b |\n")
        body = _non_blank(doc.body)
        table = body[1]
        assert isinstance(table, Table)
        assert "CAPTION" not in str(table)
        assert "invisible" not in str(table)


# ---------------------------------------------------------------------------
# Parsing — keyword attachment in heading body
# ---------------------------------------------------------------------------


class TestAttachmentInHeadingBody:
    """Affiliated keyword attachment works inside heading section bodies."""

    def test_caption_in_heading_body(self) -> None:
        """#+CAPTION inside a heading body is attached to the following element."""
        doc = loads("* My heading\n" "#+CAPTION: table caption\n" "| a | b |\n")
        heading = doc.children[0]
        body = _non_blank(heading.body)
        table = body[1]
        assert isinstance(table, Table)
        assert len(table.keywords) == 1
        assert isinstance(table.keywords[0], CaptionKeyword)
        assert table.keywords[0].value == "table caption"

    def test_multiple_headings_independent(self) -> None:
        """Keyword attachment in one heading does not bleed into another."""
        doc = loads(
            "* First\n"
            "#+CAPTION: for first\n"
            "| a | b |\n"
            "* Second\n"
            "| x | y |\n"
        )
        h1_body = _non_blank(doc.children[0].body)
        h2_body = _non_blank(doc.children[1].body)
        first_table = h1_body[1]
        second_table = h2_body[0]
        assert isinstance(first_table, Table)
        assert isinstance(second_table, Table)
        assert len(first_table.keywords) == 1
        assert len(second_table.keywords) == 0


# ---------------------------------------------------------------------------
# Parsing — keyword attachment in list item bodies
# ---------------------------------------------------------------------------


class TestAttachmentInListItemBody:
    """Affiliated keyword attachment works inside list item continuation bodies."""

    def test_caption_in_list_item_body(self) -> None:
        """#+CAPTION inside a list item body is attached to the following element."""
        doc = loads("- item one\n" "  #+CAPTION: nested caption\n" "  | a | b |\n")
        body = _non_blank(doc.body)
        lst = body[0]
        assert isinstance(lst, List)
        item = lst.items[0]
        item_body = _non_blank(item.body)
        table = item_body[1]
        assert isinstance(table, Table)
        assert len(table.keywords) == 1
        assert isinstance(table.keywords[0], CaptionKeyword)
        assert table.keywords[0].value == "nested caption"
