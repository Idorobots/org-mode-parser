"""Shared strict parsing helpers for ``from_source`` constructors.

These helpers centralize parse-then-extract flows used by semantic
``from_source`` class methods.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from org_parser._lang import PARSER

if TYPE_CHECKING:
    from collections.abc import Callable

    from org_parser.document._document import Document

__all__ = ["parse_document_from_source", "parse_source_with_extractor"]

_ExtractedT = TypeVar("_ExtractedT")


def parse_document_from_source(source: str, *, filename: str = "") -> Document:
    """Parse *source* and return a strict parse-backed :class:`Document`.

    Args:
        source: Org source text to parse.
        filename: Optional filename assigned to the parsed document.

    Returns:
        The parsed semantic :class:`Document`.

    Raises:
        ValueError: If the parse tree contains any error or missing nodes.
    """
    source_bytes = source.encode()
    tree = PARSER.parse(source_bytes)

    from org_parser.document._document import Document

    document = Document.from_tree(tree, filename, source_bytes)
    if len(document.errors) > 0:
        raise ValueError("Source contains parse errors")
    return document


def parse_source_with_extractor(
    source: str,
    *,
    extractor: Callable[[Document], _ExtractedT | None],
) -> tuple[_ExtractedT, Document]:
    """Parse *source*, validate syntax, and extract one semantic value.

    Args:
        source: Org source text to parse.
        extractor: Callback that receives ``document`` and returns
            the specific semantic value to return.

    Returns:
        A ``(extracted, document)`` tuple.

    Raises:
        ValueError: If the source cannot be parsed cleanly or no valid value is
            extracted.
    """
    source_bytes = source.encode()
    tree = PARSER.parse(source_bytes)

    from org_parser.document._document import Document

    document = Document.from_tree(tree, "", source_bytes)
    if len(document.errors) > 0:
        raise ValueError("Source contains parse errors")

    extracted = extractor(document)
    if extracted is None:
        raise ValueError("Unexpected parse tree structure")
    return extracted, document
