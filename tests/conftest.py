"""Shared pytest fixtures for the org-parser test suite."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture(scope="session")
def examples_dir() -> Path:
    """Return the absolute path to the repository's ``examples/`` directory."""
    return Path(__file__).parent.parent / "examples"


@pytest.fixture(scope="session")
def example_file(examples_dir: Path) -> Callable[[str], Path]:
    """Return a helper that resolves a filename inside ``examples/``."""

    def _resolve(name: str) -> Path:
        p = examples_dir / name
        if not p.exists():
            pytest.skip(f"Example file not found: {p}")
        return p

    return _resolve
