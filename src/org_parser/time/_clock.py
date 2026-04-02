"""Implementation of [org_parser.time.Clock][] for Org ``CLOCK:`` log lines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import node_source
from org_parser.element._element import Element, build_semantic_repr
from org_parser.time._timestamp import Timestamp

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = ["Clock"]


class Clock(Element):
    """Clock log line element.

    Args:
        timestamp: Parsed clock timestamp, if present.
        duration: Optional ``H:MM`` duration value.
        parent: Optional parent owner object.

    Example:
    ```python
    >>> from org_parser.time import Clock, Timestamp
    >>> clock = Clock(timestamp=Timestamp.from_source("<2026-03-29 Sun 10:00-11:00>"))
    >>> clock.duration
    '1:00'
    >>> clock.timestamp.start.year
    2026
    ```
    """

    def __init__(
        self,
        *,
        timestamp: Timestamp | None = None,
        duration: str | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._timestamp = timestamp
        if self._timestamp is not None:
            self._timestamp.parent = self
        self._duration = _normalize_duration(duration)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Clock:
        """Create a [org_parser.time.Clock][] from a tree-sitter ``clock`` node."""
        clock = cls(
            timestamp=_extract_clock_timestamp(node, document),
            duration=_extract_clock_duration(node, document),
            parent=parent,
        )
        clock._node = node
        clock._document = document
        return clock

    @property
    def timestamp(self) -> Timestamp | None:
        """Clock timestamp value, when present.

        Example:
        ```python
        >>> from org_parser.time import Clock, Timestamp
        >>> clock = Clock(timestamp=Timestamp.from_source("[2026-03-29 Sun 10:00-11:00]"))
        >>> clock.timestamp.start.year
        2026
        ```
        """
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value: Timestamp | None) -> None:
        """Set clock timestamp and recompute duration for ranged timestamps."""
        self._timestamp = value
        if self._timestamp is not None:
            self._timestamp.parent = self
        if value is not None and value.end is not None:
            self._duration = _duration_from_timestamp(value)
        else:
            self._duration = None
        self.mark_dirty()

    @property
    def duration(self) -> str | None:
        """Clock duration text in ``H:MM`` format, when present.

        Example:
        ```python
        >>> from org_parser.time import Clock, Timestamp
        >>> clock = Clock(timestamp=Timestamp.from_source("[2026-03-29 Sun 10:00-11:00]"))
        >>> clock.duration
        '1:00'
        ```
        """
        return self._duration

    @duration.setter
    def duration(self, value: str | None) -> None:
        """Set duration text."""
        self._duration = _normalize_duration(value)
        self.mark_dirty()

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return build_semantic_repr("Clock", timestamp=self._timestamp, duration=self._duration)

    def reformat(self) -> None:
        """Mark timestamp and this clock dirty for scratch-built rendering."""
        if self._timestamp is not None:
            self._timestamp.reformat()
        self.mark_dirty()

    def __str__(self) -> str:
        """Render clock line.

        Clean parse-backed instances preserve their verbatim source text.
        Dirty instances are rendered from semantic fields.
        """
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)

        if self._timestamp is not None and self._duration is not None:
            return f"CLOCK: {self._timestamp} =>  {self._duration}\n"
        if self._timestamp is not None:
            return f"CLOCK: {self._timestamp}\n"
        if self._duration is not None:
            return f"CLOCK: =>  {self._duration}\n"
        return "CLOCK:\n"


def _extract_clock_timestamp(
    node: tree_sitter.Node,
    document: Document,
) -> Timestamp | None:
    """Return parsed timestamp from a ``clock`` node, if present."""
    if not node.children_by_field_name("year"):
        return None
    return Timestamp.from_node(node, document)


def _extract_clock_duration(
    node: tree_sitter.Node,
    document: Document,
) -> str | None:
    """Return ``H:MM`` duration text from a ``clock`` node, if present."""
    duration_nodes = node.children_by_field_name("duration")
    if not duration_nodes:
        return None
    source_fragment = document.source_for(node).decode()
    duration_start = duration_nodes[0].start_byte - node.start_byte
    duration_fragment = source_fragment[duration_start:].strip()
    if not duration_fragment.startswith("=>"):
        return None
    duration = duration_fragment[2:].strip()
    return duration if duration != "" else None


def _normalize_duration(value: str | None) -> str | None:
    """Normalize duration text to ``H:MM`` format when present."""
    if value is None:
        return None
    normalized = value.strip()
    if normalized == "":
        return None
    return normalized


def _duration_from_timestamp(timestamp: Timestamp) -> str:
    """Compute an ``H:MM`` duration string from timestamp start/end values."""
    if timestamp.end is None:
        raise ValueError("Timestamp has no end value")
    delta = timestamp.end - timestamp.start
    minutes_total = int(delta.total_seconds() // 60)
    sign = "-" if minutes_total < 0 else ""
    minutes_abs = abs(minutes_total)
    hours, minutes = divmod(minutes_abs, 60)
    return f"{sign}{hours}:{minutes:02d}"
