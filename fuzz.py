"""Replay tree-sitter fuzz edit snapshots from stdin.

Usage:
    cat fuzz_input.log | python fuzz.py
"""

from __future__ import annotations

import argparse
import ctypes
import re
import sys
from dataclasses import dataclass

import tree_sitter


@dataclass(frozen=True)
class Edit:
    """One contiguous text replacement edit."""

    start_byte: int
    old_end_byte: int
    new_end_byte: int
    start_point: tuple[int, int]
    old_end_point: tuple[int, int]
    new_end_point: tuple[int, int]


_HEADER_RE = re.compile(r"^\s*\d+\.\s+")
_SNAPSHOT_SEPARATOR_RE = re.compile(r"\n[ \t]*\n[ \t]*\n+")


def _load_language(lib_path: str) -> tree_sitter.Language:
    """Load and return the org tree-sitter language from a shared library."""
    lib = ctypes.CDLL(lib_path)
    lib.tree_sitter_org.restype = ctypes.c_void_p

    pythonapi = ctypes.pythonapi
    pythonapi.PyCapsule_New.restype = ctypes.py_object
    pythonapi.PyCapsule_New.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
    ]

    capsule: object = pythonapi.PyCapsule_New(
        lib.tree_sitter_org(),
        b"tree_sitter.Language",
        None,
    )
    return tree_sitter.Language(capsule)


def _sexp(tree: tree_sitter.Tree) -> str:
    """Return the tree root as an s-expression-like string."""
    return str(tree.root_node)


def _byte_to_point(data: bytes, byte_offset: int) -> tuple[int, int]:
    """Convert a byte offset to a tree-sitter point ``(row, column)``."""
    row = data.count(b"\n", 0, byte_offset)
    last_newline = data.rfind(b"\n", 0, byte_offset)
    if last_newline == -1:
        return (row, byte_offset)
    return (row, byte_offset - last_newline - 1)


def _compute_edit(before: bytes, after: bytes) -> Edit:
    """Compute one contiguous replacement edit between snapshots."""
    prefix = 0
    max_prefix = min(len(before), len(after))
    while prefix < max_prefix and before[prefix] == after[prefix]:
        prefix += 1

    before_tail = len(before)
    after_tail = len(after)
    while (
        before_tail > prefix
        and after_tail > prefix
        and before[before_tail - 1] == after[after_tail - 1]
    ):
        before_tail -= 1
        after_tail -= 1

    return Edit(
        start_byte=prefix,
        old_end_byte=before_tail,
        new_end_byte=after_tail,
        start_point=_byte_to_point(before, prefix),
        old_end_point=_byte_to_point(before, before_tail),
        new_end_point=_byte_to_point(after, after_tail),
    )


def _extract_snapshots(log_text: str) -> list[bytes]:
    """Extract ordered input snapshots from a fuzz ``--log-graphs`` block."""
    normalized = log_text.replace("\r\n", "\n").replace("\r", "\n")

    lines = normalized.splitlines(keepends=True)
    while lines and lines[0].strip() == "":
        lines.pop(0)
    if not lines:
        raise ValueError("No fuzz content found in stdin.")

    if not _HEADER_RE.match(lines[0]):
        raise ValueError(
            "Expected first non-empty line to be a fuzz-case header "
            '(for example: "  0. org - corpus - ...").'
        )

    body = "".join(lines[1:])
    incorrect_index = body.find("Incorrect parse for")
    if incorrect_index != -1:
        body = body[:incorrect_index]

    body = body.lstrip("\n")
    if body.strip() == "":
        raise ValueError("No input snapshots found after header.")

    parts = [part for part in _SNAPSHOT_SEPARATOR_RE.split(body) if part != ""]
    if len(parts) < 2:
        raise ValueError("Need at least original plus one edited snapshot.")

    snapshots: list[bytes] = []
    for part in parts:
        snapshot = part if part.endswith("\n") else f"{part}\n"
        snapshots.append(snapshot.encode("utf-8"))
    return snapshots


def _replay_snapshots(parser: tree_sitter.Parser, snapshots: list[bytes]) -> int:
    """Apply snapshot edits incrementally and compare against full parses."""
    current_text = snapshots[0]
    incremental_tree = parser.parse(current_text)
    full_tree = parser.parse(current_text)

    initial_match = _sexp(incremental_tree) == _sexp(full_tree)
    print(f"snapshots: {len(snapshots)}")
    print(f"step 0 (initial): incremental==full: {initial_match}")

    had_mismatch = not initial_match

    for index, next_text in enumerate(snapshots[1:], start=1):
        edit = _compute_edit(current_text, next_text)

        incremental_tree.edit(
            start_byte=edit.start_byte,
            old_end_byte=edit.old_end_byte,
            new_end_byte=edit.new_end_byte,
            start_point=edit.start_point,
            old_end_point=edit.old_end_point,
            new_end_point=edit.new_end_point,
        )

        incremental_tree = parser.parse(next_text, incremental_tree)
        full_tree = parser.parse(next_text)

        incremental_sexp = _sexp(incremental_tree)
        full_sexp = _sexp(full_tree)
        match = incremental_sexp == full_sexp

        print(
            f"step {index}: bytes [{edit.start_byte}:{edit.old_end_byte}]"
            f" -> [{edit.start_byte}:{edit.new_end_byte}], points "
            f"{edit.start_point} -> {edit.old_end_point}/{edit.new_end_point}, "
            f"incremental==full: {match}"
        )

        if not match:
            had_mismatch = True
            print("  full:", full_sexp)
            print("  inc :", incremental_sexp)

        current_text = next_text

    return 1 if had_mismatch else 0


def main() -> int:
    """Read a fuzz log from stdin, replay edits, and report consistency."""
    cli = argparse.ArgumentParser(
        description="Replay tree-sitter fuzz snapshots from stdin."
    )
    cli.add_argument(
        "--lib-path",
        default="tree-sitter-org/org.so",
        help="Path to compiled parser shared library.",
    )
    args = cli.parse_args()

    stdin_text = sys.stdin.read()
    if stdin_text.strip() == "":
        print("No input received on stdin.", file=sys.stderr)
        return 2

    try:
        snapshots = _extract_snapshots(stdin_text)
    except ValueError as error:
        print(f"Failed to parse fuzz input: {error}", file=sys.stderr)
        return 2

    parser = tree_sitter.Parser(_load_language(args.lib_path))
    return _replay_snapshots(parser, snapshots)


if __name__ == "__main__":
    raise SystemExit(main())
