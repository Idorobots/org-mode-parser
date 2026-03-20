"""Tests for org_parser.document.load_raw()."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import tree_sitter

from org_parser._node import is_error_node
from org_parser.document import load_raw

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_error_nodes(node: tree_sitter.Node) -> bool:
    """Return True if *node* or any of its descendants is an ERROR node."""
    if is_error_node(node):
        return True
    return any(_has_error_nodes(child) for child in node.children)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoadRaw:
    """Tests for :func:`org_parser.document.load_raw`."""

    def test_simple_org_returns_tree(self, example_file: Callable[[str], Path]) -> None:
        """Parsing simple.org returns a tree_sitter.Tree instance."""
        tree = load_raw(example_file("simple.org"))
        assert isinstance(tree, tree_sitter.Tree)

    def test_simple_org_root_type_is_document(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """The root node of simple.org has type 'document'."""
        tree = load_raw(example_file("simple.org"))
        assert tree.root_node.type == "document"

    def test_simple_org_no_error_nodes(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """simple.org parses without any ERROR nodes."""
        tree = load_raw(example_file("simple.org"))
        assert not _has_error_nodes(tree.root_node)

    def test_empty_org_returns_valid_tree(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """Parsing an empty .org file returns a valid, non-None tree."""
        tree = load_raw(example_file("empty.org"))
        assert isinstance(tree, tree_sitter.Tree)
        assert tree.root_node.type == "document"

    def test_large_org_root_is_document(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """The 1000-line large.org parses to a document node with children."""
        tree = load_raw(example_file("large.org"))
        assert tree.root_node.type == "document"
        assert tree.root_node.child_count > 0

    def test_accepts_string_path(self, example_file: Callable[[str], Path]) -> None:
        """load_raw() accepts a plain str in addition to a Path object."""
        path = example_file("simple.org")
        tree_from_str = load_raw(str(path))
        tree_from_path = load_raw(path)
        assert tree_from_str.root_node.type == tree_from_path.root_node.type

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """load_raw() raises FileNotFoundError for a non-existent path."""
        missing = tmp_path / "does_not_exist.org"
        with pytest.raises(FileNotFoundError):
            load_raw(missing)

    def test_headings_org_has_children(
        self, example_file: Callable[[str], Path]
    ) -> None:
        """heading-levels.org parses and the document has heading children."""
        tree = load_raw(example_file("heading-levels.org"))
        child_types = {child.type for child in tree.root_node.children}
        # A document with headings contains at least one 'section' node
        assert len(child_types) > 0
