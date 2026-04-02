"""Snapshot tests for all ``examples/*.org`` parser fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from org_parser.document import Document, load_raw

_EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
_SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / "examples"
_UPDATE_ENV = "ORG_PARSER_UPDATE_SNAPSHOTS"

_EXAMPLE_FILES = tuple(sorted(_EXAMPLES_DIR.glob("*.org")))


def _should_update_snapshots() -> bool:
    """Return whether snapshot files should be regenerated in-place."""
    value = os.getenv(_UPDATE_ENV, "")
    return value.lower() in {"1", "true", "yes", "on"}


def _snapshot_path_for(example_path: Path) -> Path:
    """Return the snapshot file path for one example file."""
    return _SNAPSHOT_DIR / f"{example_path.stem}.snapshot"


def _render_document_snapshot(example_path: Path) -> str:
    """Parse *example_path* and return the stable semantic snapshot string."""
    source = example_path.read_bytes()
    tree = load_raw(example_path)
    filename = f"examples/{example_path.name}"
    document = Document.from_tree(tree, filename, source)
    return repr(document)


def _assert_snapshot_sets_match() -> None:
    """Assert snapshot files exactly mirror the current example set."""
    example_stems = {example.stem for example in _EXAMPLE_FILES}
    snapshot_stems = (
        {snapshot.stem for snapshot in _SNAPSHOT_DIR.glob("*.snapshot")}
        if _SNAPSHOT_DIR.exists()
        else set()
    )
    missing = sorted(example_stems - snapshot_stems)
    extra = sorted(snapshot_stems - example_stems)
    assert (
        not missing and not extra
    ), f"Snapshot/example mismatch. Missing snapshots: {missing}. Extra snapshots: {extra}."


def test_example_snapshot_set_matches_examples() -> None:
    """The checked-in snapshot set tracks every ``examples/*.org`` file."""
    _assert_snapshot_sets_match()


@pytest.mark.parametrize("example_path", _EXAMPLE_FILES, ids=lambda path: path.name)
def test_example_snapshot_matches(example_path: Path) -> None:
    """Each example file matches its semantic snapshot."""
    snapshot_path = _snapshot_path_for(example_path)
    rendered = _render_document_snapshot(example_path)

    if _should_update_snapshots():
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(rendered)

    assert snapshot_path.exists(), (
        f"Missing snapshot for {example_path.name}: {snapshot_path}. "
        f"Regenerate with {_UPDATE_ENV}=1."
    )

    expected = snapshot_path.read_text()
    assert rendered == expected
