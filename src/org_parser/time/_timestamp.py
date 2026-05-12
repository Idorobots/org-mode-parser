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
    DELAY_TIME_UNIT,
    DELAY_VALUE,
    REPEATER_CAP_TIME_UNIT,
    REPEATER_CAP_VALUE,
    REPEATER_MARK,
    REPEATER_TIME_UNIT,
    REPEATER_VALUE,
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
    from collections.abc import Callable

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading
    from org_parser.element._list import Repeat
    from org_parser.text._rich_text import RichText
    from org_parser.time._clock import Clock


__all__ = ["Repeater", "Timestamp"]


_WEEKDAY_ABBREVIATIONS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


class Repeater:
    """Mutable repeater-like timestamp component.

    This shape is used for all timestamp repeater/delay values.
    """

    __slots__ = ("_mark", "_on_mutation", "_unit", "_value")

    def __init__(
        self,
        mark: str,
        value: int,
        unit: str,
    ) -> None:
        self._on_mutation: Callable[[], None] | None = None
        self._mark = mark
        self._value = value
        self._unit = unit

    @property
    def mark(self) -> str:
        """Repeater mark token."""
        return self._mark

    @mark.setter
    def mark(self, value: str) -> None:
        self._mark = value
        self._notify_mutation()

    @property
    def value(self) -> int:
        """Repeater numeric value."""
        return self._value

    @value.setter
    def value(self, value: int) -> None:
        self._value = value
        self._notify_mutation()

    @property
    def unit(self) -> str:
        """Repeater time unit token."""
        return self._unit

    @unit.setter
    def unit(self, value: str) -> None:
        self._unit = value
        self._notify_mutation()

    def __repr__(self) -> str:
        """Return a stable developer-facing representation."""
        return f"Repeater(mark={self.mark!r}, value={self.value!r}, unit={self.unit!r})"

    def __str__(self) -> str:
        """Render this repeater in Org repeater/delay form."""
        return f"{self.mark}{self.value}{self.unit}"

    def __eq__(self, other: object) -> bool:
        """Compare repeaters by semantic fields."""
        if not isinstance(other, Repeater):
            return NotImplemented
        return (self.mark, self.value, self.unit) == (other.mark, other.value, other.unit)

    def set_on_mutation(self, callback: Callable[[], None] | None) -> None:
        self._on_mutation = callback

    def _notify_mutation(self) -> None:
        callback = self._on_mutation
        if callback is None:
            return
        callback()


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
        repeater: Optional repeater component.
        repeater_cap: Optional repeater cap component.
        delay: Optional warning delay component.

    Example:
    ```python
    >>> from org_parser.time import Timestamp
    >>> timestamp = Timestamp.from_source("<2026-03-29 Sun 10:00>")
    >>> timestamp.start.year
    2026
    ```
    """

    __slots__ = (
        "_delay",
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
        "_repeater",
        "_repeater_cap",
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
        repeater: Repeater | None = None,
        repeater_cap: Repeater | None = None,
        delay: Repeater | None = None,
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
        self._repeater = repeater
        self._repeater_cap = repeater_cap
        self._delay = delay
        _attach_repeater_mutation(self._repeater, self.mark_dirty)
        _attach_repeater_mutation(self._repeater_cap, self.mark_dirty)
        _attach_repeater_mutation(self._delay, self.mark_dirty)
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
        repeater: Repeater | None = None
        repeater_cap: Repeater | None = None
        delay: Repeater | None = None

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

        repeater, repeater_cap, delay = _extract_repeater_delay_components(node, document)

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
            repeater=repeater,
            repeater_cap=repeater_cap,
            delay=delay,
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
    def repeater(self) -> Repeater | None:
        """Repeater component, if present."""
        return self._repeater

    @repeater.setter
    def repeater(self, value: Repeater | None) -> None:
        self._repeater = value
        _attach_repeater_mutation(self._repeater, self.mark_dirty)
        self.mark_dirty()

    @property
    def repeater_cap(self) -> Repeater | None:
        """Repeater cap component, if present."""
        return self._repeater_cap

    @repeater_cap.setter
    def repeater_cap(self, value: Repeater | None) -> None:
        self._repeater_cap = value
        _attach_repeater_mutation(self._repeater_cap, self.mark_dirty)
        self.mark_dirty()

    @property
    def delay(self) -> Repeater | None:
        """Delay component, if present."""
        return self._delay

    @delay.setter
    def delay(self, value: Repeater | None) -> None:
        self._delay = value
        _attach_repeater_mutation(self._delay, self.mark_dirty)
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
            repeater=self._repeater,
            repeater_cap=self._repeater_cap,
            delay=self._delay,
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
            self._repeater,
            self._repeater_cap,
            self._delay,
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
            other._repeater,
            other._repeater_cap,
            other._delay,
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

    repeater: str | None = None
    if ts.repeater is not None:
        if ts.repeater_cap is None:
            repeater = str(ts.repeater)
        else:
            repeater = f"{ts.repeater}/{ts.repeater_cap.value}{ts.repeater_cap.unit}"
    if repeater is not None:
        parts.append(repeater)

    delay = str(ts.delay) if ts.delay is not None else None
    if delay is not None:
        parts.append(delay)

    if not parts:
        return ""
    return " " + " ".join(parts)


def _extract_repeater_delay_components(
    node: tree_sitter.Node,
    document: Document,
) -> tuple[Repeater | None, Repeater | None, Repeater | None]:
    """Extract repeater and delay components from one timestamp node."""
    repeater_mark = _first_descendant_text(node, document, REPEATER_MARK)
    repeater_value = _first_descendant_int(node, document, REPEATER_VALUE)
    repeater_unit = _first_descendant_text(node, document, REPEATER_TIME_UNIT)
    repeater = _build_repeater_if_complete(
        mark=repeater_mark,
        value=repeater_value,
        unit=repeater_unit,
    )

    repeater_cap_value = _first_descendant_int(node, document, REPEATER_CAP_VALUE)
    repeater_cap_unit = _first_descendant_text(node, document, REPEATER_CAP_TIME_UNIT)
    repeater_cap = _build_repeater_if_complete(
        mark=repeater_mark,
        value=repeater_cap_value,
        unit=repeater_cap_unit,
    )

    delay = _build_repeater_if_complete(
        mark=_first_descendant_text(node, document, DELAY_MARK),
        value=_first_descendant_int(node, document, DELAY_VALUE),
        unit=_first_descendant_text(node, document, DELAY_TIME_UNIT),
    )
    return repeater, repeater_cap, delay


def _attach_repeater_mutation(
    repeater: Repeater | None,
    callback: Callable[[], None],
) -> None:
    """Attach mutation callback for optional repeater components."""
    if repeater is None:
        return
    repeater.set_on_mutation(callback)


def _build_repeater_if_complete(
    *,
    mark: str | None,
    value: int | None,
    unit: str | None,
) -> Repeater | None:
    """Build a repeater only when all component fields are present."""
    if mark is None and value is None and unit is None:
        return None
    if mark is None or value is None or unit is None:
        return None
    return Repeater(mark=mark, value=value, unit=unit)


def _first_descendant_text(
    node: tree_sitter.Node,
    document: Document,
    node_type: str,
) -> str | None:
    """Return decoded text for the first descendant of *node_type*."""
    candidates = _descendants_by_type(node, node_type)
    if not candidates:
        return None
    return document.source_for(candidates[0]).decode()


def _first_descendant_int(
    node: tree_sitter.Node,
    document: Document,
    node_type: str,
) -> int | None:
    """Return integer text value for the first descendant of *node_type*."""
    value = _first_descendant_text(node, document, node_type)
    return _parse_optional_int(value)


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
