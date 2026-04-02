"""Tests for clock semantic elements."""

from __future__ import annotations

from org_parser import loads
from org_parser.time import Clock, Timestamp


def test_clock_parses_open_timestamp() -> None:
    """Open clock lines expose timestamp and no duration."""
    document = loads("CLOCK: [2025-01-07 Tue 14:00]\n")

    assert isinstance(document.body[0], Clock)
    clock = document.body[0]
    assert clock.timestamp is not None
    assert str(clock.timestamp) == "[2025-01-07 Tue 14:00]"
    assert clock.duration is None


def test_clock_parses_range_and_duration() -> None:
    """Closed clock lines expose ranged timestamp and duration value."""
    document = loads("CLOCK: [2025-01-06 Mon 09:00]--[2025-01-06 Mon 11:30] =>  2:30\n")

    assert isinstance(document.body[0], Clock)
    clock = document.body[0]
    assert clock.timestamp is not None
    assert clock.timestamp.end is not None
    assert str(clock.timestamp) == "[2025-01-06 Mon 09:00]--[2025-01-06 Mon 11:30]"
    assert clock.duration == "2:30"


def test_clock_parses_duration_only() -> None:
    """Duration-only clock lines expose no timestamp value."""
    document = loads("CLOCK: =>  100:30\n")

    assert isinstance(document.body[0], Clock)
    clock = document.body[0]
    assert clock.timestamp is None
    assert clock.duration == "100:30"


def test_heading_body_uses_clock_elements() -> None:
    """Heading section body returns dedicated clock element instances."""
    document = loads("* Work\n\nCLOCK: [2025-01-07 Tue 14:00]\n")

    assert len(document.children) == 1
    from org_parser.element import BlankLine

    body = [element for element in document.children[0].body if not isinstance(element, BlankLine)]
    assert isinstance(body[0], Clock)


def test_clock_timestamp_setter_recomputes_duration() -> None:
    """Setting a ranged timestamp recomputes the clock duration value."""
    document = loads("CLOCK: [2025-01-06 Mon 09:00]\n")

    assert isinstance(document.body[0], Clock)
    clock = document.body[0]
    assert clock.duration is None

    clock.timestamp = Timestamp(
        is_active=False,
        start_year=2025,
        start_month=1,
        start_day=6,
        start_dayname="Mon",
        start_hour=9,
        start_minute=0,
        end_year=2025,
        end_month=1,
        end_day=6,
        end_dayname="Mon",
        end_hour=11,
        end_minute=45,
    )

    assert clock.duration == "2:45"
    assert clock.dirty is True
    assert document.dirty is True
    assert str(clock) == "CLOCK: [2025-01-06 Mon 09:00-11:45] =>  2:45\n"


def test_clock_timestamp_setter_clears_duration_when_end_removed() -> None:
    """Replacing a ranged timestamp with a point timestamp clears the duration.

    Regression: the old setter only recomputed duration when ``value.end`` was
    set, but never cleared ``_duration`` when switching to a point timestamp.
    A clock that previously had a range would keep the stale duration and emit
    an erroneous ``=> H:MM`` in its ``__str__`` output.
    """
    document = loads("CLOCK: [2025-01-06 Mon 09:00]--[2025-01-06 Mon 11:00] =>  2:00\n")

    assert isinstance(document.body[0], Clock)
    clock = document.body[0]
    assert clock.duration == "2:00"

    # Replace with a point (open) timestamp — no end, no duration.
    clock.timestamp = Timestamp(
        is_active=False,
        start_year=2025,
        start_month=1,
        start_day=6,
        start_dayname="Mon",
        start_hour=9,
        start_minute=0,
    )

    assert clock.duration is None
    assert str(clock) == "CLOCK: [2025-01-06 Mon 09:00]\n"


def test_clock_repr_includes_timestamp_and_duration() -> None:
    """``repr(clock)`` includes timestamp and duration fields when present."""
    clock = Clock(
        timestamp=Timestamp(
            is_active=False,
            start_year=2025,
            start_month=1,
            start_day=6,
            start_dayname="Mon",
            start_hour=9,
            start_minute=0,
        ),
        duration="2:00",
    )
    r = repr(clock)
    assert r.startswith("Clock(")
    assert "timestamp=" in r
    assert "duration='2:00'" in r
    assert "raw=" not in r
    assert "end_year=" not in r


def test_clock_repr_omits_none_fields() -> None:
    """``repr(clock)`` omits ``None``-valued fields for a minimal clock."""
    clock = Clock()
    assert repr(clock) == "Clock()"
