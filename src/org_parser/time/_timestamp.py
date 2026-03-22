"""Implementation of :class:`Timestamp` for Org timestamps.

The timestamp abstraction stores parsed date/time components and exposes
datetime-based convenience accessors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from org_parser._nodes import (
    TIMESTAMP,
    TS_DAY,
    TS_DAYNAME,
    TS_MONTH,
    TS_TIME,
    TS_YEAR,
)

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document

__all__ = ["Timestamp"]


@dataclass(slots=True)
class Timestamp:
    """Parsed Org timestamp with component-level fields.

    All fields are mutable.  Mutating any field marks the instance dirty;
    a dirty :class:`Timestamp` rebuilds its string representation from the
    component fields rather than returning the original ``raw`` source text.

    Args:
        raw: Original timestamp text from source.  Used verbatim by
            :meth:`__str__` until the instance is marked dirty.
        is_active: Whether the timestamp uses active delimiters (``<...>``).
        start_year: Start year.
        start_month: Start month (1-12).
        start_day: Start day (1-31).
        start_dayname: Optional start day name token (e.g. ``"Mon"``).
        start_hour: Optional start hour (0-23).
        start_minute: Optional start minute (0-59).
        end_year: Optional end year for ranges.
        end_month: Optional end month for ranges.
        end_day: Optional end day for ranges.
        end_dayname: Optional end day name token.
        end_hour: Optional end hour.
        end_minute: Optional end minute.
    """

    raw: str
    is_active: bool
    start_year: int
    start_month: int
    start_day: int
    start_dayname: str | None = None
    start_hour: int | None = None
    start_minute: int | None = None
    end_year: int | None = None
    end_month: int | None = None
    end_day: int | None = None
    end_dayname: str | None = None
    end_hour: int | None = None
    end_minute: int | None = None
    _dirty: bool = field(default=False, init=False, repr=False, compare=False)

    @classmethod
    def from_source(cls, source: str) -> Timestamp:
        """Parse *source* and return one strict :class:`Timestamp`.

        The source must parse to a single inline timestamp object with no
        surrounding text.

        Args:
            source: Org source text containing exactly one timestamp.

        Returns:
            Parsed :class:`Timestamp`.

        Raises:
            ValueError: If parsing fails or the structure is not one timestamp.
        """
        from org_parser.text._inline import PlainText
        from org_parser.text._rich_text import RichText

        rich_text = RichText.from_source(source)
        parts = [
            part
            for part in rich_text.parts
            if not (isinstance(part, PlainText) and str(part) == "")
        ]
        if len(parts) != 1:
            raise ValueError("Unexpected parse tree structure")
        part = parts[0]
        if not isinstance(part, cls):
            raise ValueError("Unexpected parse tree structure")
        return part

    @classmethod
    def from_node(cls, node: tree_sitter.Node, document: Document) -> Timestamp:
        """Create a :class:`Timestamp` from a tree-sitter timestamp-like node."""
        raw = _extract_raw_timestamp_text(node, document)
        is_active = raw.startswith("<")

        year_nodes = list(_descendants_by_type(node, TS_YEAR))
        month_nodes = list(_descendants_by_type(node, TS_MONTH))
        day_nodes = list(_descendants_by_type(node, TS_DAY))
        dayname_nodes = list(_descendants_by_type(node, TS_DAYNAME))
        time_nodes = list(_descendants_by_type(node, TS_TIME))

        start_year = int(document.source_for(year_nodes[0]).decode())
        start_month = int(document.source_for(month_nodes[0]).decode())
        start_day = int(document.source_for(day_nodes[0]).decode())
        start_dayname = (
            document.source_for(dayname_nodes[0]).decode()
            if len(dayname_nodes) >= 1
            else None
        )

        start_hour, start_minute = (None, None)
        if len(time_nodes) >= 1:
            start_hour, start_minute = _parse_time_components(
                document.source_for(time_nodes[0]).decode()
            )

        end_year: int | None = None
        end_month: int | None = None
        end_day: int | None = None
        end_dayname: str | None = None
        end_hour: int | None = None
        end_minute: int | None = None

        is_explicit_range = "--" in raw and len(year_nodes) >= 2
        is_same_day_time_range = "--" not in raw and len(time_nodes) >= 2

        if is_explicit_range:
            end_year = int(document.source_for(year_nodes[1]).decode())
            end_month = int(document.source_for(month_nodes[1]).decode())
            end_day = int(document.source_for(day_nodes[1]).decode())
            if len(dayname_nodes) >= 2:
                end_dayname = document.source_for(dayname_nodes[1]).decode()
        elif is_same_day_time_range:
            end_year = start_year
            end_month = start_month
            end_day = start_day
            end_dayname = start_dayname

        if end_year is not None and len(time_nodes) >= 2:
            end_hour, end_minute = _parse_time_components(
                document.source_for(time_nodes[1]).decode()
            )

        return cls(
            raw=raw,
            is_active=is_active,
            start_year=start_year,
            start_month=start_month,
            start_day=start_day,
            start_dayname=start_dayname,
            start_hour=start_hour,
            start_minute=start_minute,
            end_year=end_year,
            end_month=end_month,
            end_day=end_day,
            end_dayname=end_dayname,
            end_hour=end_hour,
            end_minute=end_minute,
        )

    @property
    def start(self) -> datetime:
        """Return the start value as :class:`datetime`."""
        hour = self.start_hour if self.start_hour is not None else 0
        minute = self.start_minute if self.start_minute is not None else 0
        return datetime(self.start_year, self.start_month, self.start_day, hour, minute)

    @property
    def end(self) -> datetime | None:
        """Return the end value as :class:`datetime`, if available."""
        if self.end_year is None or self.end_month is None or self.end_day is None:
            return None
        hour = self.end_hour if self.end_hour is not None else 0
        minute = self.end_minute if self.end_minute is not None else 0
        return datetime(self.end_year, self.end_month, self.end_day, hour, minute)

    def to_datetime(self) -> datetime:
        """Return this timestamp as :class:`datetime` using ``start``."""
        return self.start

    def __str__(self) -> str:
        """Render the timestamp as an Org source string.

        Returns the original ``raw`` text when clean.  Once dirty, rebuilds
        the string from component fields.
        """
        if not self._dirty:
            return self.raw
        return _render_timestamp(self)

    @property
    def dirty(self) -> bool:
        """Whether this timestamp has been mutated since creation."""
        return self._dirty

    def mark_dirty(self) -> None:
        """Mark this timestamp as dirty."""
        self._dirty = True

    def reformat(self) -> None:
        """Mark this timestamp as dirty for scratch-built rendering."""
        self.mark_dirty()


def _render_timestamp(ts: Timestamp) -> str:
    """Build an Org timestamp string from *ts* component fields.

    Handles all four forms:
    - Date only: ``<YYYY-MM-DD>`` or ``<YYYY-MM-DD Day>``
    - Date + time: ``<YYYY-MM-DD Day HH:MM>``
    - Same-day time range: ``<YYYY-MM-DD Day HH:MM-HH:MM>``
    - Explicit date range: ``<YYYY-MM-DD Day>--<YYYY-MM-DD Day>``

    Active timestamps use ``<...>``; inactive timestamps use ``[...]``.
    """
    open_delim = "<" if ts.is_active else "["
    close_delim = ">" if ts.is_active else "]"

    is_explicit_range = (
        ts.end_year is not None
        and ts.end_month is not None
        and ts.end_day is not None
        and (
            ts.end_year != ts.start_year
            or ts.end_month != ts.start_month
            or ts.end_day != ts.start_day
        )
    )
    is_same_day_time_range = (
        ts.end_year is not None
        and ts.end_year == ts.start_year
        and ts.end_month == ts.start_month
        and ts.end_day == ts.start_day
        and ts.end_hour is not None
        and ts.end_minute is not None
    )

    if is_explicit_range:
        end_year = ts.end_year
        end_month = ts.end_month
        end_day = ts.end_day
        assert end_year is not None and end_month is not None and end_day is not None
        start = _render_date_part(
            ts.start_year,
            ts.start_month,
            ts.start_day,
            ts.start_dayname,
            ts.start_hour,
            ts.start_minute,
        )
        end = _render_date_part(
            end_year,
            end_month,
            end_day,
            ts.end_dayname,
            ts.end_hour,
            ts.end_minute,
        )
        return f"{open_delim}{start}{close_delim}--{open_delim}{end}{close_delim}"

    if is_same_day_time_range:
        assert ts.end_hour is not None and ts.end_minute is not None
        date_part = _render_date_part(
            ts.start_year,
            ts.start_month,
            ts.start_day,
            ts.start_dayname,
            ts.start_hour,
            ts.start_minute,
        )
        end_time = f"{ts.end_hour:02d}:{ts.end_minute:02d}"
        return f"{open_delim}{date_part}-{end_time}{close_delim}"

    date_part = _render_date_part(
        ts.start_year,
        ts.start_month,
        ts.start_day,
        ts.start_dayname,
        ts.start_hour,
        ts.start_minute,
    )
    return f"{open_delim}{date_part}{close_delim}"


def _render_date_part(
    year: int,
    month: int,
    day: int,
    dayname: str | None,
    hour: int | None,
    minute: int | None,
) -> str:
    """Render the inner content of one timestamp bracket.

    Args:
        year: Four-digit year.
        month: Month (1-12).
        day: Day of month (1-31).
        dayname: Optional abbreviated day name (e.g. ``"Mon"``).
        hour: Optional hour (0-23).
        minute: Optional minute (0-59).

    Returns:
        A string like ``"2024-01-15 Mon 14:30"`` (time parts omitted when
        *hour* / *minute* are ``None``).
    """
    parts = [f"{year:04d}-{month:02d}-{day:02d}"]
    if dayname is not None:
        parts.append(dayname)
    if hour is not None and minute is not None:
        parts.append(f"{hour:02d}:{minute:02d}")
    return " ".join(parts)


def _extract_raw_timestamp_text(node: tree_sitter.Node, document: Document) -> str:
    """Return timestamp text slice for one timestamp-like parser node."""
    if node.type == TIMESTAMP:
        return document.source_for(node).decode()

    value_nodes = node.children_by_field_name("value")
    if not value_nodes:
        raise ValueError("Node does not contain a timestamp value")
    first = value_nodes[0].start_byte
    last = value_nodes[-1].end_byte
    text = document.source_for(node).decode()
    relative_start = first - node.start_byte
    relative_end = last - node.start_byte
    return text[relative_start:relative_end]


def _descendants_by_type(
    node: tree_sitter.Node,
    node_type: str,
) -> list[tree_sitter.Node]:
    """Return descendants of *node* with the given *node_type* in source order."""
    matches: list[tree_sitter.Node] = []
    stack: list[tree_sitter.Node] = [node]
    while stack:
        current = stack.pop()
        if current.type == node_type:
            matches.append(current)
        stack.extend(reversed(current.named_children))
    return matches


def _parse_time_components(value: str) -> tuple[int, int]:
    """Return ``(hour, minute)`` from an ``HH:MM`` string."""
    hour_text, minute_text = value.split(":", 1)
    return int(hour_text), int(minute_text)
