"""Implementation of [org_parser.time.Timestamp][] for Org timestamps.

The timestamp abstraction stores parsed date/time components and exposes
datetime-based convenience accessors.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from org_parser._node import report_internal_parse_errors
from org_parser._nodes import (
    DELAY_MARK,
    REPEATER_MARK,
    TIME_UNIT,
    TIMESTAMP,
    TS_DAY,
    TS_DAYNAME,
    TS_MONTH,
    TS_TIME,
    TS_YEAR,
)
from org_parser.element._element import build_semantic_repr
from org_parser.text import InlineObject

if TYPE_CHECKING:
    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading
    from org_parser.element._list import Repeat
    from org_parser.text._rich_text import RichText
    from org_parser.time._clock import Clock


__all__ = ["Timestamp"]


_WEEKDAY_ABBREVIATIONS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class Timestamp(InlineObject):
    """Parsed Org timestamp with component-level fields.

    All fields are mutable.  Mutating any field marks the instance dirty;
    a dirty [org_parser.time.Timestamp][] rebuilds its string representation from the
    component fields rather than returning the original ``raw`` source text.

    Args:
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
        repeater_mark: Optional repeater mark (``+``, ``++``, ``.+``).
        repeater_value: Optional repeater numeric value.
        repeater_unit: Optional repeater unit (``h``, ``d``, ``w``, ``m``, ``y``).
        repeater_cap_value: Optional upper-bound numeric value for repeaters.
        repeater_cap_unit: Optional upper-bound unit for repeaters.
        delay_mark: Optional warning-delay mark (``-`` or ``--``).
        delay_value: Optional warning-delay numeric value.
        delay_unit: Optional warning-delay unit (``h``, ``d``, ``w``, ``m``, ``y``).

    Example:
    ```python
    >>> from org_parser.time import Timestamp
    >>> timestamp = Timestamp.from_source("<2026-03-29 Sun 10:00>")
    >>> timestamp.start.year
    2026
    ```
    """

    __slots__ = (
        "_delay_mark",
        "_delay_unit",
        "_delay_value",
        "_dirty",
        "_end_day",
        "_end_dayname",
        "_end_hour",
        "_end_minute",
        "_end_month",
        "_end_year",
        "_is_active",
        "_parent",
        "_raw",
        "_repeater_cap_unit",
        "_repeater_cap_value",
        "_repeater_mark",
        "_repeater_unit",
        "_repeater_value",
        "_start_day",
        "_start_dayname",
        "_start_hour",
        "_start_minute",
        "_start_month",
        "_start_year",
    )

    def __init__(
        self,
        *,
        is_active: bool,
        start_year: int,
        start_month: int,
        start_day: int,
        start_dayname: str | None = None,
        start_hour: int | None = None,
        start_minute: int | None = None,
        end_year: int | None = None,
        end_month: int | None = None,
        end_day: int | None = None,
        end_dayname: str | None = None,
        end_hour: int | None = None,
        end_minute: int | None = None,
        repeater_mark: str | None = None,
        repeater_value: int | None = None,
        repeater_unit: str | None = None,
        repeater_cap_value: int | None = None,
        repeater_cap_unit: str | None = None,
        delay_mark: str | None = None,
        delay_value: int | None = None,
        delay_unit: str | None = None,
        parent: Heading | Clock | Repeat | RichText | None = None,
    ) -> None:
        """Initialize a mutable timestamp value."""
        self._is_active = is_active
        self._start_year = start_year
        self._start_month = start_month
        self._start_day = start_day
        self._start_dayname = start_dayname
        self._start_hour = start_hour
        self._start_minute = start_minute
        self._end_year = end_year
        self._end_month = end_month
        self._end_day = end_day
        self._end_dayname = end_dayname
        self._end_hour = end_hour
        self._end_minute = end_minute
        self._repeater_mark = repeater_mark
        self._repeater_value = repeater_value
        self._repeater_unit = repeater_unit
        self._repeater_cap_value = repeater_cap_value
        self._repeater_cap_unit = repeater_cap_unit
        self._delay_mark = delay_mark
        self._delay_value = delay_value
        self._delay_unit = delay_unit
        self._parent = parent
        self._dirty = False
        self._raw = _render_timestamp(self)

    @classmethod
    def from_source(cls, source: str) -> Timestamp:
        """Parse *source* and return one strict [org_parser.time.Timestamp][].

        The source must parse to a single inline timestamp object with no
        surrounding text.

        Args:
            source: Org source text containing exactly one timestamp.

        Returns:
            Parsed [org_parser.time.Timestamp][].

        Raises:
            ValueError: If parsing fails or the structure is not one timestamp.
            TypeError: If the parsed inline object is not a timestamp.
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
            raise TypeError("Unexpected parse tree structure")
        return part

    @classmethod
    def from_datetime(
        cls,
        value: datetime,
        *,
        is_active: bool = True,
    ) -> Timestamp:
        """Create a timestamp from one Python ``datetime`` start value.

        The datetime is mapped onto the timestamp start components. End,
        repeater, and delay components are left unset.

        Args:
            value: Source datetime for the timestamp start components.
            is_active: Whether to render the timestamp with active delimiters.
        """
        return cls(
            is_active=is_active,
            start_year=value.year,
            start_month=value.month,
            start_day=value.day,
            start_dayname=_WEEKDAY_ABBREVIATIONS[value.weekday()],
            start_hour=value.hour,
            start_minute=value.minute,
        )

    @classmethod
    def from_node(cls, node: tree_sitter.Node, document: Document) -> Timestamp:
        """Create a [org_parser.time.Timestamp][] from a tree-sitter timestamp-like node."""
        report_internal_parse_errors(node, document)
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
            document.source_for(dayname_nodes[0]).decode() if len(dayname_nodes) >= 1 else None
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
        repeater_mark: str | None = None
        repeater_value: int | None = None
        repeater_unit: str | None = None
        repeater_cap_value: int | None = None
        repeater_cap_unit: str | None = None
        delay_mark: str | None = None
        delay_value: int | None = None
        delay_unit: str | None = None

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

        (
            repeater_mark,
            repeater_value,
            repeater_unit,
            repeater_cap_value,
            repeater_cap_unit,
            delay_mark,
            delay_value,
            delay_unit,
        ) = _extract_repeater_delay_components(node, document)

        parsed = cls(
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
            repeater_mark=repeater_mark,
            repeater_value=repeater_value,
            repeater_unit=repeater_unit,
            repeater_cap_value=repeater_cap_value,
            repeater_cap_unit=repeater_cap_unit,
            delay_mark=delay_mark,
            delay_value=delay_value,
            delay_unit=delay_unit,
        )
        parsed._raw = raw
        return parsed

    @property
    def parent(self) -> Heading | Clock | Repeat | RichText | None:
        """Parent object that owns this timestamp, if any."""
        return self._parent

    @parent.setter
    def parent(self, value: Heading | Clock | Repeat | RichText | None) -> None:
        """Set parent owner without changing dirty state."""
        self._parent = value

    @property
    def is_active(self) -> bool:
        """Whether this timestamp uses active delimiters (``<...>``)."""
        return self._is_active

    @is_active.setter
    def is_active(self, value: bool) -> None:
        """Set delimiter activity and mark dirty."""
        self._is_active = value
        self.mark_dirty()

    @property
    def start_year(self) -> int:
        """Start year value."""
        return self._start_year

    @start_year.setter
    def start_year(self, value: int) -> None:
        """Set start year and mark dirty."""
        self._start_year = value
        self.mark_dirty()

    @property
    def start_month(self) -> int:
        """Start month value."""
        return self._start_month

    @start_month.setter
    def start_month(self, value: int) -> None:
        """Set start month and mark dirty."""
        self._start_month = value
        self.mark_dirty()

    @property
    def start_day(self) -> int:
        """Start day value."""
        return self._start_day

    @start_day.setter
    def start_day(self, value: int) -> None:
        """Set start day and mark dirty."""
        self._start_day = value
        self.mark_dirty()

    @property
    def start_dayname(self) -> str | None:
        """Optional start day-name token."""
        return self._start_dayname

    @start_dayname.setter
    def start_dayname(self, value: str | None) -> None:
        """Set start day-name token and mark dirty."""
        self._start_dayname = value
        self.mark_dirty()

    @property
    def start_hour(self) -> int | None:
        """Optional start hour."""
        return self._start_hour

    @start_hour.setter
    def start_hour(self, value: int | None) -> None:
        """Set start hour and mark dirty."""
        self._start_hour = value
        self.mark_dirty()

    @property
    def start_minute(self) -> int | None:
        """Optional start minute."""
        return self._start_minute

    @start_minute.setter
    def start_minute(self, value: int | None) -> None:
        """Set start minute and mark dirty."""
        self._start_minute = value
        self.mark_dirty()

    @property
    def end_year(self) -> int | None:
        """Optional end year for ranges."""
        return self._end_year

    @end_year.setter
    def end_year(self, value: int | None) -> None:
        """Set end year and mark dirty."""
        self._end_year = value
        self.mark_dirty()

    @property
    def end_month(self) -> int | None:
        """Optional end month for ranges."""
        return self._end_month

    @end_month.setter
    def end_month(self, value: int | None) -> None:
        """Set end month and mark dirty."""
        self._end_month = value
        self.mark_dirty()

    @property
    def end_day(self) -> int | None:
        """Optional end day for ranges."""
        return self._end_day

    @end_day.setter
    def end_day(self, value: int | None) -> None:
        """Set end day and mark dirty."""
        self._end_day = value
        self.mark_dirty()

    @property
    def end_dayname(self) -> str | None:
        """Optional end day-name token."""
        return self._end_dayname

    @end_dayname.setter
    def end_dayname(self, value: str | None) -> None:
        """Set end day-name token and mark dirty."""
        self._end_dayname = value
        self.mark_dirty()

    @property
    def end_hour(self) -> int | None:
        """Optional end hour for ranges."""
        return self._end_hour

    @end_hour.setter
    def end_hour(self, value: int | None) -> None:
        """Set end hour and mark dirty."""
        self._end_hour = value
        self.mark_dirty()

    @property
    def end_minute(self) -> int | None:
        """Optional end minute for ranges."""
        return self._end_minute

    @end_minute.setter
    def end_minute(self, value: int | None) -> None:
        """Set end minute and mark dirty."""
        self._end_minute = value
        self.mark_dirty()

    @property
    def repeater_mark(self) -> str | None:
        """Optional repeater mark (``+``, ``++``, ``.+``)."""
        return self._repeater_mark

    @repeater_mark.setter
    def repeater_mark(self, value: str | None) -> None:
        """Set repeater mark and mark dirty."""
        self._repeater_mark = value
        self.mark_dirty()

    @property
    def repeater_value(self) -> int | None:
        """Optional repeater numeric value."""
        return self._repeater_value

    @repeater_value.setter
    def repeater_value(self, value: int | None) -> None:
        """Set repeater numeric value and mark dirty."""
        self._repeater_value = value
        self.mark_dirty()

    @property
    def repeater_unit(self) -> str | None:
        """Optional repeater unit (``h``, ``d``, ``w``, ``m``, ``y``)."""
        return self._repeater_unit

    @repeater_unit.setter
    def repeater_unit(self, value: str | None) -> None:
        """Set repeater unit and mark dirty."""
        self._repeater_unit = value
        self.mark_dirty()

    @property
    def repeater_cap_value(self) -> int | None:
        """Optional repeater upper-bound numeric value."""
        return self._repeater_cap_value

    @repeater_cap_value.setter
    def repeater_cap_value(self, value: int | None) -> None:
        """Set repeater upper-bound numeric value and mark dirty."""
        self._repeater_cap_value = value
        self.mark_dirty()

    @property
    def repeater_cap_unit(self) -> str | None:
        """Optional repeater upper-bound unit (``h``, ``d``, ``w``, ``m``, ``y``)."""
        return self._repeater_cap_unit

    @repeater_cap_unit.setter
    def repeater_cap_unit(self, value: str | None) -> None:
        """Set repeater upper-bound unit and mark dirty."""
        self._repeater_cap_unit = value
        self.mark_dirty()

    @property
    def delay_mark(self) -> str | None:
        """Optional delay mark (``-`` or ``--``)."""
        return self._delay_mark

    @delay_mark.setter
    def delay_mark(self, value: str | None) -> None:
        """Set delay mark and mark dirty."""
        self._delay_mark = value
        self.mark_dirty()

    @property
    def delay_value(self) -> int | None:
        """Optional delay numeric value."""
        return self._delay_value

    @delay_value.setter
    def delay_value(self, value: int | None) -> None:
        """Set delay numeric value and mark dirty."""
        self._delay_value = value
        self.mark_dirty()

    @property
    def delay_unit(self) -> str | None:
        """Optional delay unit (``h``, ``d``, ``w``, ``m``, ``y``)."""
        return self._delay_unit

    @delay_unit.setter
    def delay_unit(self, value: str | None) -> None:
        """Set delay unit and mark dirty."""
        self._delay_unit = value
        self.mark_dirty()

    @property
    def start(self) -> datetime:
        """Return the start value as `datetime.datetime`.

        Example:
        ```python
        >>> from org_parser.time import Timestamp
        >>> timestamp = Timestamp.from_source("<2026-03-29 Sun 10:00>")
        >>> timestamp.start.year
        2026
        ```
        """
        hour = self.start_hour if self.start_hour is not None else 0
        minute = self.start_minute if self.start_minute is not None else 0
        return datetime(self.start_year, self.start_month, self.start_day, hour, minute)

    @property
    def end(self) -> datetime | None:
        """Return the end value as `datetime.datetime`, if available.

        Example:
        ```python
        >>> from org_parser.time import Timestamp
        >>> timestamp = Timestamp.from_source("<2026-03-29 Sun 10:00-20:00>")
        >>> timestamp.end is not None
        True
        ```
        """
        if self.end_year is None or self.end_month is None or self.end_day is None:
            return None
        hour = self.end_hour if self.end_hour is not None else 0
        minute = self.end_minute if self.end_minute is not None else 0
        return datetime(self.end_year, self.end_month, self.end_day, hour, minute)

    def to_datetime(self) -> datetime:
        """Return this timestamp as `datetime.datetime` using ``start``.

        Example:
        ```python
        >>> from org_parser.time import Timestamp
        >>> timestamp = Timestamp.from_source("<2026-03-29 Sun 10:00>")
        >>> timestamp.to_datetime()
        datetime.datetime(2026, 3, 29, 10, 0)
        ```
        """
        return self.start

    def __str__(self) -> str:
        """Render the timestamp as an Org source string.

        Returns the original source text when clean. Once dirty, rebuilds
        the string from component fields.
        """
        if not self._dirty:
            return self._raw
        return _render_timestamp(self)

    def __repr__(self) -> str:
        """Return a developer-friendly semantic representation."""
        return build_semantic_repr(
            "Timestamp",
            is_active=self.is_active,
            start_year=self.start_year,
            start_month=self.start_month,
            start_day=self.start_day,
            start_dayname=self.start_dayname,
            start_hour=self.start_hour,
            start_minute=self.start_minute,
            end_year=self.end_year,
            end_month=self.end_month,
            end_day=self.end_day,
            end_dayname=self.end_dayname,
            end_hour=self.end_hour,
            end_minute=self.end_minute,
            repeater_mark=self.repeater_mark,
            repeater_value=self.repeater_value,
            repeater_unit=self.repeater_unit,
            repeater_cap_value=self.repeater_cap_value,
            repeater_cap_unit=self.repeater_cap_unit,
            delay_mark=self.delay_mark,
            delay_value=self.delay_value,
            delay_unit=self.delay_unit,
        )

    def __eq__(self, other: object) -> bool:
        """Compare timestamps by semantic component fields only."""
        if not isinstance(other, Timestamp):
            return NotImplemented
        return (
            self.is_active,
            self.start_year,
            self.start_month,
            self.start_day,
            self.start_dayname,
            self.start_hour,
            self.start_minute,
            self.end_year,
            self.end_month,
            self.end_day,
            self.end_dayname,
            self.end_hour,
            self.end_minute,
            self.repeater_mark,
            self.repeater_value,
            self.repeater_unit,
            self.repeater_cap_value,
            self.repeater_cap_unit,
            self.delay_mark,
            self.delay_value,
            self.delay_unit,
        ) == (
            other.is_active,
            other.start_year,
            other.start_month,
            other.start_day,
            other.start_dayname,
            other.start_hour,
            other.start_minute,
            other.end_year,
            other.end_month,
            other.end_day,
            other.end_dayname,
            other.end_hour,
            other.end_minute,
            other.repeater_mark,
            other.repeater_value,
            other.repeater_unit,
            other.repeater_cap_value,
            other.repeater_cap_unit,
            other.delay_mark,
            other.delay_value,
            other.delay_unit,
        )

    @property
    def dirty(self) -> bool:
        """Whether this timestamp has been mutated since creation."""
        return self._dirty

    def mark_dirty(self) -> None:
        """Mark this timestamp dirty and bubble to parent chain."""
        if self._dirty:
            return
        self._dirty = True
        parent = self._parent
        if parent is None:
            return
        parent.mark_dirty()

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
    repeater_delay_suffix = _render_repeater_delay_suffix(ts)

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
        if ts.end_year is None or ts.end_month is None or ts.end_day is None:
            raise ValueError("Invalid timestamp state for explicit end-date range")
        start = _render_date_part(
            ts.start_year,
            ts.start_month,
            ts.start_day,
            ts.start_dayname,
            ts.start_hour,
            ts.start_minute,
            repeater_delay_suffix,
        )
        end = _render_date_part(
            ts.end_year,
            ts.end_month,
            ts.end_day,
            ts.end_dayname,
            ts.end_hour,
            ts.end_minute,
        )
        return f"{open_delim}{start}{close_delim}--{open_delim}{end}{close_delim}"

    if is_same_day_time_range:
        if ts.end_hour is None or ts.end_minute is None:
            raise ValueError("Invalid timestamp state for same-day end-time range")
        date_part = _render_date_part(
            ts.start_year,
            ts.start_month,
            ts.start_day,
            ts.start_dayname,
            ts.start_hour,
            ts.start_minute,
        )
        end_time = f"{ts.end_hour:02d}:{ts.end_minute:02d}"
        return f"{open_delim}{date_part}-{end_time}{repeater_delay_suffix}{close_delim}"

    date_part = _render_date_part(
        ts.start_year,
        ts.start_month,
        ts.start_day,
        ts.start_dayname,
        ts.start_hour,
        ts.start_minute,
        repeater_delay_suffix,
    )
    return f"{open_delim}{date_part}{close_delim}"


def _render_date_part(
    year: int,
    month: int,
    day: int,
    dayname: str | None,
    hour: int | None,
    minute: int | None,
    repeater_delay_suffix: str = "",
) -> str:
    """Render the inner content of one timestamp bracket.

    Args:
        year: Four-digit year.
        month: Month (1-12).
        day: Day of month (1-31).
        dayname: Optional abbreviated day name (e.g. ``"Mon"``).
        hour: Optional hour (0-23).
        minute: Optional minute (0-59).
        repeater_delay_suffix: Optional rendered repeater/delay suffix.

    Returns:
        A string like ``"2024-01-15 Mon 14:30"`` (time parts omitted when
        *hour* / *minute* are ``None``).
    """
    parts = [f"{year:04d}-{month:02d}-{day:02d}"]
    if dayname is not None:
        parts.append(dayname)
    if hour is not None and minute is not None:
        parts.append(f"{hour:02d}:{minute:02d}")
    return " ".join(parts) + repeater_delay_suffix


def _render_repeater_delay_suffix(ts: Timestamp) -> str:
    """Render repeater and delay components for one timestamp bracket."""
    parts: list[str] = []

    repeater = _render_mark_component(
        mark=ts.repeater_mark,
        value=ts.repeater_value,
        unit=ts.repeater_unit,
        cap_value=ts.repeater_cap_value,
        cap_unit=ts.repeater_cap_unit,
    )
    if repeater is not None:
        parts.append(repeater)

    delay = _render_mark_component(
        mark=ts.delay_mark,
        value=ts.delay_value,
        unit=ts.delay_unit,
    )
    if delay is not None:
        parts.append(delay)

    if not parts:
        return ""
    return " " + " ".join(parts)


def _render_mark_component(
    *,
    mark: str | None,
    value: int | None,
    unit: str | None,
    cap_value: int | None = None,
    cap_unit: str | None = None,
) -> str | None:
    """Render one repeater/delay component when complete."""
    if mark is None or value is None or unit is None:
        return None
    rendered = f"{mark}{value}{unit}"
    if cap_value is not None and cap_unit is not None:
        rendered += f"/{cap_value}{cap_unit}"
    return rendered


def _extract_repeater_delay_components(
    node: tree_sitter.Node,
    document: Document,
) -> tuple[
    str | None,
    int | None,
    str | None,
    int | None,
    str | None,
    str | None,
    int | None,
    str | None,
]:
    """Extract repeater and delay components from one timestamp node."""
    mark_nodes = list(node.children_by_field_name("mark"))
    unit_nodes = [
        candidate
        for candidate in node.children_by_field_name("unit")
        if candidate.type == TIME_UNIT
    ]
    cap_unit_nodes = [
        candidate
        for candidate in node.children_by_field_name("cap_unit")
        if candidate.type == TIME_UNIT
    ]

    if not mark_nodes or not unit_nodes:
        return (None, None, None, None, None, None, None, None)

    source_text = document.source_for(node).decode()
    repeater: tuple[str | None, int | None, str | None, int | None, str | None] = (
        None,
        None,
        None,
        None,
        None,
    )
    delay: tuple[str | None, int | None, str | None] = (None, None, None)

    cap_index = 0
    for index, mark_node in enumerate(mark_nodes):
        if index >= len(unit_nodes):
            break
        unit_node = unit_nodes[index]
        if unit_node.start_byte < mark_node.end_byte:
            continue

        mark_text = document.source_for(mark_node).decode()
        unit_text = document.source_for(unit_node).decode()
        value = _parse_optional_int(
            source_text[
                mark_node.end_byte - node.start_byte : unit_node.start_byte - node.start_byte
            ].strip()
        )
        cap_value, cap_unit_text, cap_index = _extract_repeater_cap_component(
            node=node,
            source_text=source_text,
            document=document,
            unit_node=unit_node,
            next_mark_start=(
                mark_nodes[index + 1].start_byte if index + 1 < len(mark_nodes) else None
            ),
            cap_unit_nodes=cap_unit_nodes,
            cap_index=cap_index,
        )

        if mark_node.type == REPEATER_MARK and repeater[0] is None:
            repeater = (mark_text, value, unit_text, cap_value, cap_unit_text)
            continue

        if mark_node.type == DELAY_MARK and delay[0] is None:
            delay = (mark_text, value, unit_text)

    return (
        repeater[0],
        repeater[1],
        repeater[2],
        repeater[3],
        repeater[4],
        delay[0],
        delay[1],
        delay[2],
    )


def _extract_repeater_cap_component(
    *,
    node: tree_sitter.Node,
    source_text: str,
    document: Document,
    unit_node: tree_sitter.Node,
    next_mark_start: int | None,
    cap_unit_nodes: list[tree_sitter.Node],
    cap_index: int,
) -> tuple[int | None, str | None, int]:
    """Extract optional repeater cap component for one mark/unit pair."""
    while cap_index < len(cap_unit_nodes):
        cap_unit_node = cap_unit_nodes[cap_index]
        if cap_unit_node.start_byte <= unit_node.end_byte:
            cap_index += 1
            continue
        if next_mark_start is not None and cap_unit_node.start_byte >= next_mark_start:
            break

        span = source_text[
            unit_node.end_byte - node.start_byte : cap_unit_node.start_byte - node.start_byte
        ]
        slash_index = span.find("/")
        if slash_index == -1:
            break

        cap_text = span[slash_index + 1 :].strip()
        cap_value = _parse_optional_int(cap_text)
        cap_unit_text = document.source_for(cap_unit_node).decode()
        return cap_value, cap_unit_text, cap_index + 1

    return None, None, cap_index


def _parse_optional_int(value: str | None) -> int | None:
    """Return integer value parsed from text, or ``None``."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


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
