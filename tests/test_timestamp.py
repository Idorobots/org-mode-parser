"""Tests for :class:`Timestamp` mutability and dirty-aware rendering."""

from __future__ import annotations

import pytest

from org_parser.time import Timestamp


def _make_ts(**kwargs: object) -> Timestamp:
    """Construct a minimal active date-only :class:`Timestamp`."""
    defaults: dict[str, object] = {
        "raw": "<2024-01-15 Mon>",
        "is_active": True,
        "start_year": 2024,
        "start_month": 1,
        "start_day": 15,
        "start_dayname": "Mon",
    }
    defaults.update(kwargs)
    return Timestamp(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Dirty flag
# ---------------------------------------------------------------------------


def test_timestamp_is_clean_after_construction() -> None:
    """A freshly constructed timestamp is not dirty."""
    ts = _make_ts()
    assert ts.dirty is False


def test_mark_dirty_sets_dirty_flag() -> None:
    """``mark_dirty()`` sets the dirty flag."""
    ts = _make_ts()
    ts.mark_dirty()
    assert ts.dirty is True


def test_reformat_sets_dirty_flag() -> None:
    """``reformat()`` sets the dirty flag."""
    ts = _make_ts()
    ts.reformat()
    assert ts.dirty is True


def test_mutating_field_does_not_auto_set_dirty() -> None:
    """Fields are mutable; callers are responsible for calling mark_dirty."""
    ts = _make_ts()
    ts.start_year = 2025
    # The dataclass does not auto-track mutations; dirty must be set explicitly.
    assert ts.dirty is False


# ---------------------------------------------------------------------------
# __str__ — clean path returns raw
# ---------------------------------------------------------------------------


def test_str_clean_returns_raw() -> None:
    """A clean timestamp renders as its original ``raw`` text."""
    raw = "<2024-01-15 Mon>"
    ts = _make_ts(raw=raw)
    assert str(ts) == raw


def test_str_clean_inactive_returns_raw() -> None:
    """A clean inactive timestamp renders as its original ``raw`` text."""
    raw = "[2024-01-15 Mon]"
    ts = _make_ts(raw=raw, is_active=False)
    assert str(ts) == raw


# ---------------------------------------------------------------------------
# __str__ — dirty path rebuilds from components
# ---------------------------------------------------------------------------


def test_str_dirty_date_only_active() -> None:
    """Dirty active date-only timestamp renders without time."""
    ts = _make_ts(raw="<stale>")
    ts.start_year = 2026
    ts.start_month = 3
    ts.start_day = 5
    ts.start_dayname = "Thu"
    ts.mark_dirty()
    assert str(ts) == "<2026-03-05 Thu>"


def test_str_dirty_date_only_inactive() -> None:
    """Dirty inactive date-only timestamp uses ``[...]`` delimiters."""
    ts = _make_ts(raw="[stale]", is_active=False)
    ts.mark_dirty()
    assert str(ts) == "[2024-01-15 Mon]"


def test_str_dirty_date_only_no_dayname() -> None:
    """Dirty timestamp without a dayname omits it from output."""
    ts = _make_ts(raw="<stale>", start_dayname=None)
    ts.mark_dirty()
    assert str(ts) == "<2024-01-15>"


def test_str_dirty_with_time() -> None:
    """Dirty timestamp with start time renders ``HH:MM`` component."""
    ts = _make_ts(raw="<stale>", start_hour=14, start_minute=30)
    ts.mark_dirty()
    assert str(ts) == "<2024-01-15 Mon 14:30>"


def test_str_dirty_with_time_zero_padded() -> None:
    """Hour and minute values are zero-padded to two digits."""
    ts = _make_ts(raw="<stale>", start_hour=9, start_minute=5)
    ts.mark_dirty()
    assert str(ts) == "<2024-01-15 Mon 09:05>"


def test_str_dirty_same_day_time_range() -> None:
    """Dirty same-day time range renders as ``HH:MM-HH:MM`` within one bracket."""
    ts = _make_ts(
        raw="<stale>",
        start_hour=10,
        start_minute=0,
        end_year=2024,
        end_month=1,
        end_day=15,
        end_dayname="Mon",
        end_hour=12,
        end_minute=0,
    )
    ts.mark_dirty()
    assert str(ts) == "<2024-01-15 Mon 10:00-12:00>"


def test_str_dirty_explicit_date_range_active() -> None:
    """Dirty explicit date range renders as ``<start>--<end>``."""
    ts = _make_ts(
        raw="<stale>",
        end_year=2024,
        end_month=1,
        end_day=20,
        end_dayname="Sat",
    )
    ts.mark_dirty()
    assert str(ts) == "<2024-01-15 Mon>--<2024-01-20 Sat>"


def test_str_dirty_explicit_date_range_inactive() -> None:
    """Dirty explicit date range uses ``[...]`` delimiters when inactive."""
    ts = _make_ts(
        raw="[stale]",
        is_active=False,
        end_year=2024,
        end_month=1,
        end_day=20,
        end_dayname="Sat",
    )
    ts.mark_dirty()
    assert str(ts) == "[2024-01-15 Mon]--[2024-01-20 Sat]"


def test_str_dirty_explicit_date_range_with_times() -> None:
    """Dirty explicit date range with times on both ends renders correctly."""
    ts = _make_ts(
        raw="<stale>",
        start_hour=9,
        start_minute=0,
        end_year=2024,
        end_month=1,
        end_day=20,
        end_dayname="Sat",
        end_hour=17,
        end_minute=30,
    )
    ts.mark_dirty()
    assert str(ts) == "<2024-01-15 Mon 09:00>--<2024-01-20 Sat 17:30>"


# ---------------------------------------------------------------------------
# Field mutation round-trips
# ---------------------------------------------------------------------------


def test_mutate_year_and_render() -> None:
    """Mutating start_year and marking dirty produces correct output."""
    ts = _make_ts(raw="<2024-01-15 Mon>")
    ts.start_year = 2030
    ts.mark_dirty()
    assert str(ts) == "<2030-01-15 Mon>"


def test_mutate_active_flag_and_render() -> None:
    """Flipping is_active changes delimiter style when dirty."""
    ts = _make_ts(raw="<2024-01-15 Mon>", is_active=True)
    ts.is_active = False
    ts.mark_dirty()
    assert str(ts) == "[2024-01-15 Mon]"


def test_add_time_to_date_only_timestamp() -> None:
    """Adding time components to a date-only timestamp renders the time."""
    ts = _make_ts(raw="<2024-01-15 Mon>")
    ts.start_hour = 8
    ts.start_minute = 0
    ts.mark_dirty()
    assert str(ts) == "<2024-01-15 Mon 08:00>"


# ---------------------------------------------------------------------------
# Comparison is unaffected by _dirty
# ---------------------------------------------------------------------------


def test_dirty_flag_excluded_from_equality() -> None:
    """Two timestamps with identical fields are equal regardless of dirty state."""
    ts1 = _make_ts()
    ts2 = _make_ts()
    ts2.mark_dirty()
    assert ts1 == ts2


# ---------------------------------------------------------------------------
# Cross-month and cross-year explicit range rendering (regression for
# is_explicit_range day-only comparison bug)
# ---------------------------------------------------------------------------


def test_str_dirty_cross_month_range_not_collapsed() -> None:
    """Cross-month range with the same day-of-month renders as explicit range.

    Regression: the old check ``end_day != start_day`` misclassified a range
    like Jan-15 → Feb-15 as a same-day time range, silently dropping the end
    date when the timestamp was dirty.
    """
    ts = _make_ts(
        raw="<stale>",
        start_dayname="Wed",
        end_year=2024,
        end_month=2,
        end_day=15,
        end_dayname="Thu",
    )
    ts.mark_dirty()
    assert str(ts) == "<2024-01-15 Wed>--<2024-02-15 Thu>"


def test_str_dirty_cross_year_range_same_day_not_collapsed() -> None:
    """Cross-year range with the same month and day renders as explicit range."""
    ts = _make_ts(
        raw="<stale>",
        start_dayname="Mon",
        end_year=2025,
        end_month=1,
        end_day=15,
        end_dayname="Wed",
    )
    ts.mark_dirty()
    assert str(ts) == "<2024-01-15 Mon>--<2025-01-15 Wed>"


def test_str_dirty_same_day_time_range_still_works_after_fix() -> None:
    """Same-day time range (start/end same date, different times) is unaffected."""
    ts = _make_ts(
        raw="<stale>",
        start_hour=9,
        start_minute=0,
        end_year=2024,
        end_month=1,
        end_day=15,
        end_dayname="Mon",
        end_hour=11,
        end_minute=30,
    )
    ts.mark_dirty()
    assert str(ts) == "<2024-01-15 Mon 09:00-11:30>"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("year", "month", "day", "expected"),
    [
        (2024, 1, 1, "<2024-01-01 Mon>"),
        (2024, 12, 31, "<2024-12-31 Mon>"),
        (999, 6, 9, "<0999-06-09 Mon>"),
    ],
)
def test_str_dirty_date_zero_padding(
    year: int, month: int, day: int, expected: str
) -> None:
    """Year, month, and day are always zero-padded in dirty rendering."""
    ts = _make_ts(raw="<stale>", start_year=year, start_month=month, start_day=day)
    ts.mark_dirty()
    assert str(ts) == expected
