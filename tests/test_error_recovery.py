"""Tests for parse-error recovery: ParseError, Document.errors, and related.

These tests verify that:
- Clean documents have an empty ``errors`` list.
- Programmatically constructed documents have an empty ``errors`` list.
- :func:`element_from_error_or_unknown` recovers ERROR nodes as
  :class:`~org_parser.element._paragraph.Paragraph` objects and records
  the error via :meth:`Document.report_error`.
- :func:`element_from_error_or_unknown` returns a plain :class:`Element` for
  unrecognised but valid (non-error) nodes without recording an error.
- :class:`ParseError` fields are accessible and immutable (frozen dataclass).
- The ``str()`` of a recovered error :class:`Paragraph` returns verbatim text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from org_parser.document import Document, ParseError, load_raw
from org_parser.element._element import Element, element_from_error_or_unknown
from org_parser.element._paragraph import Paragraph

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
    return node


def _make_fake_missing_node(text: str = "MISSING text") -> MagicMock:
    """Return a mock tree-sitter node with ``is_missing = True``."""
    node = MagicMock()
    node.type = "some_token"
    node.is_missing = True
    encoded = text.encode()
    node.start_byte = 0
    node.end_byte = len(encoded)
    return node


def _make_fake_valid_node(node_type: str = "unknown_node") -> MagicMock:
    """Return a mock tree-sitter node that is syntactically valid but unknown."""
    node = MagicMock()
    node.type = node_type
    node.is_missing = False
    text = b"some text"
    node.start_byte = 0
    node.end_byte = len(text)
    # Element.from_node accesses node.text attribute indirectly; ensure needed attrs
    node.children = []
    node.named_children = []
    return node


# ---------------------------------------------------------------------------
# ParseError dataclass
# ---------------------------------------------------------------------------


class TestParseError:
    """Tests for the :class:`ParseError` frozen dataclass."""

    def test_fields_accessible(self) -> None:
        """ParseError.node and ParseError.text are readable."""
        fake_node = _make_fake_error_node("bad text")
        err = ParseError(node=fake_node, text="bad text")
        assert err.node is fake_node
        assert err.text == "bad text"

    def test_frozen(self) -> None:
        """ParseError cannot be mutated after construction."""
        import dataclasses

        import pytest

        fake_node = _make_fake_error_node()
        err = ParseError(node=fake_node, text="x")
        assert dataclasses.is_dataclass(err)
        with pytest.raises(dataclasses.FrozenInstanceError):
            err.text = "y"  # type: ignore[misc]

    def test_equality(self) -> None:
        """Two ParseError instances with the same values are equal."""
        fake_node = _make_fake_error_node()
        err1 = ParseError(node=fake_node, text="abc")
        err2 = ParseError(node=fake_node, text="abc")
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

    def test_from_tree_simple_org_has_no_errors(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """simple.org parses without any recorded errors."""
        doc = _load_document(example_file("simple.org"))
        assert doc.errors == []

    def test_from_tree_empty_org_has_no_errors(
        self, example_file: Callable[[str], Path]
    ) -> None:
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
    """Return a minimal :class:`Document` whose ``source`` is *source_bytes*."""
    doc = Document(filename="<test>")
    doc.source = source_bytes
    return doc


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
        assert doc.errors[0].node is node

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
        assert doc.errors[0].node is node

    def test_unknown_valid_node_returns_element(self) -> None:
        """An unknown but syntactically valid node returns a plain Element."""
        node = _make_fake_valid_node("unknown_node")
        result = element_from_error_or_unknown(node)
        assert type(result) is Element

    def test_unknown_valid_node_does_not_record_error(self) -> None:
        """Document.errors is NOT updated for unknown valid nodes."""
        doc = _make_doc_with_source(b"some text")
        node = _make_fake_valid_node("unknown_node")
        element_from_error_or_unknown(node, doc)
        assert doc.errors == []

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
