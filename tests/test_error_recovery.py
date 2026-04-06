"""Tests for parse-error recovery: ParseError, Document.errors, and related.

These tests verify that:
- Clean documents have an empty ``errors`` list.
- Programmatically constructed documents have an empty ``errors`` list.
- :func:`element_from_error_or_unknown` recovers ERROR nodes as
  :class:`~org_parser.element._paragraph.Paragraph` objects and records
  the error via :meth:`Document.report_error`.
- :func:`element_from_error_or_unknown` recovers unrecognised but valid nodes
  as :class:`~org_parser.element._paragraph.Paragraph` objects and records
  the error via :meth:`Document.report_error`.
- :class:`ParseError` fields are accessible and immutable (frozen dataclass).
- The ``str()`` of a recovered error :class:`Paragraph` returns verbatim text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from org_parser.document import Document, ParseError, load_raw
from org_parser.element._element import element_from_error_or_unknown
from org_parser.element._paragraph import Paragraph
from org_parser.text import RichText

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


def _parse_source(source: str) -> Document:
    """Parse an org source string into a :class:`Document`."""
    from org_parser._lang import PARSER

    src_bytes = source.encode()
    tree = PARSER.parse(src_bytes)
    return Document.from_tree(tree, "<test>", src_bytes)


def _make_fake_error_node(text: str = "ERROR text") -> MagicMock:
    """Return a mock tree-sitter node that looks like an ERROR node."""
    node = MagicMock()
    node.type = "ERROR"
    node.is_missing = False
    encoded = text.encode()
    node.start_byte = 0
    node.end_byte = len(encoded)
    node.start_point = (0, 0)
    node.end_point = (0, len(encoded))
    return node


def _make_fake_missing_node(text: str = "MISSING text") -> MagicMock:
    """Return a mock tree-sitter node with ``is_missing = True``."""
    node = MagicMock()
    node.type = "some_token"
    node.is_missing = True
    encoded = text.encode()
    node.start_byte = 0
    node.end_byte = len(encoded)
    node.start_point = (0, 0)
    node.end_point = (0, len(encoded))
    return node


def _make_fake_valid_node(node_type: str = "unknown_node") -> MagicMock:
    """Return a mock tree-sitter node that is syntactically valid but unknown."""
    node = MagicMock()
    node.type = node_type
    node.is_missing = False
    text = b"some text"
    node.start_byte = 0
    node.end_byte = len(text)
    node.start_point = (0, 0)
    node.end_point = (0, len(text))
    node.children = []
    node.named_children = []
    return node


# ---------------------------------------------------------------------------
# ParseError dataclass
# ---------------------------------------------------------------------------


def _make_parse_error(text: str = "ERROR text") -> ParseError:
    """Construct a :class:`ParseError` from a fake error node."""
    node = _make_fake_error_node(text)
    return ParseError(
        start_point=node.start_point,
        end_point=node.end_point,
        text=text,
        _node=node,
    )


class TestParseError:
    """Tests for the :class:`ParseError` frozen dataclass."""

    def test_fields_accessible(self) -> None:
        """ParseError.start_point, end_point, and text are readable."""
        err = _make_parse_error("bad text")
        assert err.start_point == (0, 0)
        assert err.end_point == (0, len(b"bad text"))
        assert err.text == "bad text"
        assert err.message == "Unexpected parse node"

    def test_frozen(self) -> None:
        """ParseError cannot be mutated after construction."""
        import dataclasses

        import pytest

        err = _make_parse_error()
        assert dataclasses.is_dataclass(err)
        with pytest.raises(dataclasses.FrozenInstanceError):
            err.text = "y"  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two ParseError instances with the same values are equal."""
        fake_node = _make_fake_error_node()
        err1 = ParseError(
            start_point=fake_node.start_point,
            end_point=fake_node.end_point,
            text="abc",
            _node=fake_node,
        )
        err2 = ParseError(
            start_point=fake_node.start_point,
            end_point=fake_node.end_point,
            text="abc",
            _node=fake_node,
        )
        assert err1 == err2


# ---------------------------------------------------------------------------
# Document.errors — clean documents
# ---------------------------------------------------------------------------


class TestDocumentErrorsClean:
    """Tests that clean documents have no errors."""

    def test_programmatic_document_has_empty_errors(self) -> None:
        """Programmatically constructed Document.errors is empty."""
        doc = Document(filename="test.org")
        assert doc.errors == []

    def test_report_error_without_source_raises_value_error(self) -> None:
        """Programmatic documents cannot report node errors without source bytes."""
        import pytest

        doc = Document(filename="test.org")
        node = _make_fake_error_node("ERROR text")
        with pytest.raises(ValueError):
            doc.report_error(node)

    def test_report_error_uses_explicit_message(self) -> None:
        """report_error stores caller-provided semantic message overrides."""
        doc = _make_doc_with_source(b"ERROR text")
        node = _make_fake_error_node("ERROR text")

        doc.report_error(node, "custom message")

        assert len(doc.errors) == 1
        assert doc.errors[0].message == "custom message"

    def test_source_for_without_source_raises_value_error(self) -> None:
        """Programmatic documents cannot slice source without source bytes."""
        import pytest

        doc = Document(filename="test.org")
        node = _make_fake_error_node("ERROR text")
        with pytest.raises(ValueError):
            doc.source_for(node)

    def test_source_for_returns_full_source_and_node_slice(self) -> None:
        """source_for returns bytes for requested node spans."""
        from org_parser._lang import PARSER

        source = b"* Heading\n"
        tree = PARSER.parse(source)
        root = tree.root_node
        node = root.children[0]
        doc = Document.from_tree(tree, "<test>", source)
        assert doc.source_for(node) == source[node.start_byte : node.end_byte]
        assert doc.source_for(root) == source[root.start_byte : root.end_byte]

    def test_rich_text_from_node_without_source_raises_value_error(self) -> None:
        """Source-backed from_node paths reject documents without source bytes."""
        import pytest

        from org_parser._lang import PARSER

        node = PARSER.parse(b"plain text\n").root_node
        doc = Document(filename="test.org")
        with pytest.raises(ValueError):
            RichText.from_node(node, document=doc)

    def test_from_tree_simple_org_has_no_errors(self, example_file: Callable[[str], Path]) -> None:
        """simple.org parses without any recorded errors."""
        doc = _load_document(example_file("simple.org"))
        assert doc.errors == []

    def test_from_tree_empty_org_has_no_errors(self, example_file: Callable[[str], Path]) -> None:
        """empty.org parses without any recorded errors."""
        doc = _load_document(example_file("empty.org"))
        assert doc.errors == []

    def test_clean_source_no_errors(self) -> None:
        """A well-formed org string produces no parse errors."""
        src = "#+TITLE: Test\n\n* Heading\n\nSome paragraph text.\n"
        doc = _parse_source(src)
        assert doc.errors == []


# ---------------------------------------------------------------------------
# element_from_error_or_unknown — unit tests
# ---------------------------------------------------------------------------


def _make_doc_with_source(source_bytes: bytes) -> Document:
    """Return a minimal parse-backed :class:`Document` for *source_bytes*."""
    from org_parser._lang import PARSER

    parse_source = source_bytes if source_bytes.endswith(b"\n") else source_bytes + b"\n"
    tree = PARSER.parse(parse_source)
    return Document.from_tree(tree, "<test>", parse_source)


class TestElementFromErrorOrUnknown:
    """Unit tests for :func:`element_from_error_or_unknown`."""

    def test_error_node_returns_paragraph(self) -> None:
        """ERROR node is recovered as a Paragraph."""
        node = _make_fake_error_node("ERROR text")
        result = element_from_error_or_unknown(node)
        assert isinstance(result, Paragraph)

    def test_error_node_str_returns_verbatim_text(self) -> None:
        """str() of the recovered Paragraph returns the verbatim error text."""
        text = "bad [[link\n"
        source = text.encode()
        doc = _make_doc_with_source(source)
        node = _make_fake_error_node(text)
        node.end_byte = len(source)
        result = element_from_error_or_unknown(node, doc)
        assert isinstance(result, Paragraph)
        assert str(result) == text

    def test_error_node_records_error_on_document(self) -> None:
        """ERROR node is recorded via Document.report_error."""
        source = b"ERROR text"
        doc = _make_doc_with_source(source)
        node = _make_fake_error_node("ERROR text")
        element_from_error_or_unknown(node, doc)
        assert len(doc.errors) == 1
        assert doc.errors[0].text == "ERROR text"
        assert doc.errors[0].start_point == (0, 0)
        assert doc.errors[0].message == "Encountered parser ERROR node"

    def test_missing_node_returns_paragraph(self) -> None:
        """A missing node is recovered as a Paragraph."""
        node = _make_fake_missing_node("MISSING text")
        result = element_from_error_or_unknown(node)
        assert isinstance(result, Paragraph)

    def test_missing_node_records_error_on_document(self) -> None:
        """Missing node is recorded via Document.report_error."""
        source = b"MISSING text"
        doc = _make_doc_with_source(source)
        node = _make_fake_missing_node("MISSING text")
        element_from_error_or_unknown(node, doc)
        assert len(doc.errors) == 1
        assert doc.errors[0].text == "MISSING text"
        assert doc.errors[0].start_point == (0, 0)
        assert doc.errors[0].message == "Encountered parser MISSING node: some_token"

    def test_unknown_valid_node_returns_paragraph(self) -> None:
        """An unknown but syntactically valid node is recovered as a Paragraph."""
        node = _make_fake_valid_node("unknown_node")
        result = element_from_error_or_unknown(node)
        assert isinstance(result, Paragraph)

    def test_unknown_valid_node_records_error(self) -> None:
        """Document.errors IS updated for unknown valid nodes."""
        doc = _make_doc_with_source(b"some text")
        node = _make_fake_valid_node("unknown_node")
        element_from_error_or_unknown(node, doc)
        assert len(doc.errors) == 1
        assert doc.errors[0].text == "some text"
        assert doc.errors[0].message == "Unexpected parse node"

    def test_no_document_does_not_raise(self) -> None:
        """Calling without document does not raise."""
        node = _make_fake_error_node("ERROR text")
        result = element_from_error_or_unknown(node)
        assert isinstance(result, Paragraph)

    def test_parent_is_set_on_recovered_paragraph(self) -> None:
        """The recovered Paragraph has the correct parent assigned."""
        node = _make_fake_error_node("ERROR text")
        fake_parent = MagicMock()
        result = element_from_error_or_unknown(node, parent=fake_parent)
        assert isinstance(result, Paragraph)
        assert result.parent is fake_parent


# ---------------------------------------------------------------------------
# Phase 2 — Document-level and Heading-level ERROR recovery
# ---------------------------------------------------------------------------


class TestDocumentRootErrorRecovery:
    """ERROR nodes that are direct children of the document root node."""

    def test_bare_properties_drawer_syntax_produces_error(self) -> None:
        """':properties:\\n' parses as an ERROR at the document root."""
        doc = _parse_source(":properties:\n")
        assert len(doc.errors) == 1

    def test_bare_properties_drawer_error_recovered_in_body(self) -> None:
        """The recovered element from a root ERROR is added to doc.body."""
        doc = _parse_source(":properties:\n")
        assert len(doc.body) == 1
        assert isinstance(doc.body[0], Paragraph)

    def test_bare_properties_drawer_error_text(self) -> None:
        """The recovered Paragraph str() matches the verbatim error text."""
        src = ":properties:\n"
        doc = _parse_source(src)
        assert str(doc.body[0]) == src

    def test_root_error_before_heading_both_recorded(self) -> None:
        """Root ERROR before a valid heading: error recorded, heading kept."""
        doc = _parse_source("<<target\n* heading\n")
        assert len(doc.errors) >= 1
        assert len(doc.children) == 1

    def test_clean_source_still_has_no_errors(self) -> None:
        """A valid source string continues to produce zero errors."""
        doc = _parse_source("* heading\n\nsome text\n")
        assert doc.errors == []


class TestHeadingChildErrorRecovery:
    """ERROR nodes that are direct children of a heading node."""

    def test_incomplete_properties_under_heading_produces_error(self) -> None:
        """'* test\\n:properties:\\n' records an error on the document."""
        doc = _parse_source("* test\n:properties:\n")
        assert len(doc.errors) == 1

    def test_incomplete_properties_under_heading_error_text(self) -> None:
        """The error text matches the verbatim ERROR node source span."""
        doc = _parse_source("* test\n:properties:\n")
        assert doc.errors[0].text == ":properties:\n"

    def test_incomplete_properties_under_heading_recovered_in_body(self) -> None:
        """The recovered element is appended to the heading's body."""
        doc = _parse_source("* test\n:properties:\n")
        heading = doc.children[0]
        assert len(heading.body) >= 1
        assert any(isinstance(e, Paragraph) for e in heading.body)

    def test_incomplete_properties_heading_still_parsed(self) -> None:
        """The heading itself is still built with correct title."""
        doc = _parse_source("* test\n:properties:\n")
        assert len(doc.children) == 1
        heading = doc.children[0]
        assert str(heading.title) == "test"

    def test_heading_with_valid_body_has_no_errors(self) -> None:
        """A heading with a valid properties drawer records no errors."""
        doc = _parse_source("* test\n:PROPERTIES:\n:key: value\n:END:\n")
        assert doc.errors == []


class TestZerothSectionErrorRecovery:
    """ERROR nodes that appear inside the zeroth section (before any heading)."""

    def test_error_inside_zeroth_section_is_recorded(self) -> None:
        """An ERROR node inside zeroth_section is recorded in doc.errors."""
        # '<<unclosed' is an incomplete link target and parses as an ERROR
        # named child of zeroth_section, exercising the else-branch of
        # _parse_zeroth_section via extract_body_element.
        doc = _parse_source("#+TITLE: Doc\n<<unclosed\n* Heading\n")
        assert len(doc.errors) >= 1

    def test_error_inside_zeroth_section_recovered_in_body(self) -> None:
        """The recovered element from a zeroth-section ERROR lands in doc.body."""
        doc = _parse_source("#+TITLE: Doc\n<<unclosed\n* Heading\n")
        assert any(isinstance(e, Paragraph) for e in doc.body)

    def test_error_inside_zeroth_section_heading_still_parsed(self) -> None:
        """A heading following a zeroth-section ERROR is still parsed."""
        doc = _parse_source("#+TITLE: Doc\n<<unclosed\n* Heading\n")
        assert len(doc.children) == 1
        assert str(doc.children[0].title) == "Heading"

    def test_error_inside_zeroth_section_keyword_still_extracted(self) -> None:
        """Keywords before the ERROR in the zeroth section are still extracted."""
        doc = _parse_source("#+TITLE: Doc\n<<unclosed\n* Heading\n")
        assert doc.title is not None
        assert str(doc.title) == "Doc"


class TestObjectInternalErrorPercolation:
    """Errors nested inside semantic objects are reported on document."""

    def test_invalid_planning_timestamp_reports_document_error(self) -> None:
        """Planning timestamps with internal parse errors percolate to document."""
        doc = _parse_source("* Heading\nSCHEDULED: <2025-12-12, at some point>\n")
        assert any(error.text == ", at some point" for error in doc.errors)

    def test_invalid_clock_timestamp_reports_document_error(self) -> None:
        """Clock timestamps with internal parse errors percolate to document."""
        doc = _parse_source("CLOCK: [2025-12-12, at some point]\n")
        assert any(error.text == ", at some point" for error in doc.errors)
