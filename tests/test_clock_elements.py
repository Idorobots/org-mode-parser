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
    body = [
        element
        for element in document.children[0].body
        if getattr(element, "node_type", "") != "blank_line"
    ]
    assert isinstance(body[0], Clock)


def test_clock_timestamp_setter_recomputes_duration() -> None:
    """Setting a ranged timestamp recomputes the clock duration value."""
    document = loads("CLOCK: [2025-01-06 Mon 09:00]\n")

    assert isinstance(document.body[0], Clock)
    clock = document.body[0]
    assert clock.duration is None

    clock.timestamp = Timestamp(
        raw="[2025-01-06 Mon 09:00]--[2025-01-06 Mon 11:45]",
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
    assert (
        str(clock) == "CLOCK: [2025-01-06 Mon 09:00]--[2025-01-06 Mon 11:45] =>  2:45\n"
    )
