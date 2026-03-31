"""Semantic recovery helpers for affiliated-keyword attachment."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._list import List

if TYPE_CHECKING:
    from org_parser.element._element import Element
    from org_parser.element._keyword import AffiliatedKeyword

__all__ = ["attach_affiliated_keywords"]


def attach_affiliated_keywords(body: list[Element]) -> None:
    """Attach affiliated keywords to the element immediately following them.

    Each affiliated keyword (``#+CAPTION:``, ``#+TBLNAME:``, ``#+PLOT:``,
    ``#+RESULTS:``) found in *body* is attached to the next
    non-affiliated-keyword element via
    [org_parser.element.Element.attach_keyword][]. If a trailing
    sequence of affiliated keywords has no following element they are left
    unattached. Keywords are **not** removed from *body*.

    The scan recurses into nested container element streams (for example list
    item bodies, indent bodies, drawer bodies, and container block bodies).

    Args:
        body: The body element stream to process.
    """
    _attach_recursively(body)


def _attach_recursively(elements: list[Element]) -> None:
    """Attach affiliated keywords in one stream and recurse into containers."""
    _attach_in_stream(elements)
    for element in elements:
        for child_stream in _child_streams(element):
            _attach_recursively(child_stream)


def _attach_in_stream(body: list[Element]) -> None:
    """Attach pending affiliated keywords within one flat element stream."""
    from org_parser.element._keyword import AffiliatedKeyword

    pending: list[AffiliatedKeyword] = []
    for element in body:
        if isinstance(element, AffiliatedKeyword):
            pending.append(element)
            continue

        for kw in pending:
            element.attach_keyword(kw)
        pending.clear()


def _child_streams(element: Element) -> list[list[Element]]:
    """Return nested child element streams for recursive keyword attachment."""
    streams: list[list[Element]] = []

    if isinstance(element, List):
        streams.extend(item.body for item in element.items)
        return streams

    body = getattr(element, "body", None)
    if isinstance(body, list):
        streams.append(body)

    return streams
