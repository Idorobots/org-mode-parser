"""Implementation of :class:`Timestamp` for Org timestamps.

The timestamp abstraction stores parsed date/time components and exposes
datetime-based convenience accessors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from org_parser._node import node_text
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

__all__ = ["Timestamp"]


@dataclass(frozen=True, slots=True)
class Timestamp:
    """Parsed Org timestamp with component-level fields.

    Args:
        raw: Original timestamp text from source.
        is_active: Whether the timestamp uses active delimiters (``<...>``).
        start_year: Start year.
        start_month: Start month.
        start_day: Start day.
        start_dayname: Optional start day name token.
        start_hour: Optional start hour.
        start_minute: Optional start minute.
        end_year: Optional end year for ranges / durations.
        end_month: Optional end month for ranges / durations.
        end_day: Optional end day for ranges / durations.
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
    def from_node(cls, node: tree_sitter.Node, source: bytes) -> Timestamp:
        """Create a :class:`Timestamp` from a tree-sitter timestamp-like node."""
        raw = _extract_raw_timestamp_text(node, source)
        is_active = raw.startswith("<")

        year_nodes = list(_descendants_by_type(node, TS_YEAR))
        month_nodes = list(_descendants_by_type(node, TS_MONTH))
        day_nodes = list(_descendants_by_type(node, TS_DAY))
        dayname_nodes = list(_descendants_by_type(node, TS_DAYNAME))
        time_nodes = list(_descendants_by_type(node, TS_TIME))

        start_year = int(node_text(year_nodes[0], source))
        start_month = int(node_text(month_nodes[0], source))
        start_day = int(node_text(day_nodes[0], source))
        start_dayname = (
            node_text(dayname_nodes[0], source) if len(dayname_nodes) >= 1 else None
        )

        start_hour, start_minute = (None, None)
        if len(time_nodes) >= 1:
            start_hour, start_minute = _parse_time_components(
                node_text(time_nodes[0], source)
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
            end_year = int(node_text(year_nodes[1], source))
            end_month = int(node_text(month_nodes[1], source))
            end_day = int(node_text(day_nodes[1], source))
            if len(dayname_nodes) >= 2:
                end_dayname = node_text(dayname_nodes[1], source)
        elif is_same_day_time_range:
            end_year = start_year
            end_month = start_month
            end_day = start_day
            end_dayname = start_dayname

        if end_year is not None and len(time_nodes) >= 2:
            end_hour, end_minute = _parse_time_components(
                node_text(time_nodes[1], source)
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
        """Render timestamp as original source text."""
        return self.raw

    @property
    def dirty(self) -> bool:
        """Whether this timestamp has been marked for reformatting."""
        return self._dirty

    def mark_dirty(self) -> None:
        """Mark this timestamp as dirty."""
        if self._dirty:
            return
        object.__setattr__(self, "_dirty", True)

    def reformat(self) -> None:
        """Mark this timestamp as dirty for scratch-built rendering."""
        self.mark_dirty()


def _extract_raw_timestamp_text(node: tree_sitter.Node, source: bytes) -> str:
    """Return timestamp text slice for one timestamp-like parser node."""
    if node.type == TIMESTAMP:
        return source[node.start_byte : node.end_byte].decode()

    value_nodes = node.children_by_field_name("value")
    if not value_nodes:
        raise ValueError("Node does not contain a timestamp value")
    return source[value_nodes[0].start_byte : value_nodes[-1].end_byte].decode()


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
