"""Implementation of :class:`Clock` for Org ``CLOCK:`` log lines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._element import Element
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
        source_text: Optional verbatim source text.
    """

    def __init__(
        self,
        *,
        timestamp: Timestamp | None = None,
        duration: str | None = None,
        parent: Document | Heading | Element | None = None,
        source_text: str = "",
    ) -> None:
        super().__init__(node_type="clock", source_text=source_text, parent=parent)
        self._timestamp = timestamp
        self._duration = _normalize_duration(duration)

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        source: bytes,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> Clock:
        """Create a :class:`Clock` from a tree-sitter ``clock`` node."""
        source_text = source[node.start_byte : node.end_byte].decode()
        clock = cls(
            timestamp=_extract_clock_timestamp(node, source),
            duration=_extract_clock_duration(node, source),
            parent=parent,
            source_text=source_text,
        )
        clock._node = node
        return clock

    @property
    def timestamp(self) -> Timestamp | None:
        """Clock timestamp value, when present."""
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value: Timestamp | None) -> None:
        """Set clock timestamp and recompute duration for ranged timestamps."""
        self._timestamp = value
        if value is not None and value.end is not None:
            self._duration = _duration_from_timestamp(value)
        self._mark_dirty()

    @property
    def duration(self) -> str | None:
        """Clock duration text in ``H:MM`` format, when present."""
        return self._duration

    @duration.setter
    def duration(self, value: str | None) -> None:
        """Set duration text and mark this clock element as dirty."""
        self._duration = _normalize_duration(value)
        self._mark_dirty()

    def __str__(self) -> str:
        """Render clock line.

        Clean parse-backed instances preserve their verbatim source text.
        Dirty instances are rendered from semantic fields.
        """
        if not self.dirty and self._node is not None:
            return self.source_text

        if self._timestamp is not None and self._duration is not None:
            return f"CLOCK: {self._timestamp} =>  {self._duration}\n"
        if self._timestamp is not None:
            return f"CLOCK: {self._timestamp}\n"
        if self._duration is not None:
            return f"CLOCK: =>  {self._duration}\n"
        return "CLOCK:\n"


def _extract_clock_timestamp(node: tree_sitter.Node, source: bytes) -> Timestamp | None:
    """Return parsed timestamp from a ``clock`` node, if present."""
    if not node.children_by_field_name("year"):
        return None
    return Timestamp.from_node(node, source)


def _extract_clock_duration(node: tree_sitter.Node, source: bytes) -> str | None:
    """Return ``H:MM`` duration text from a ``clock`` node, if present."""
    duration_nodes = node.children_by_field_name("duration")
    if not duration_nodes:
        return None
    duration_fragment = (
        source[duration_nodes[0].start_byte : node.end_byte].decode().strip()
    )
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
