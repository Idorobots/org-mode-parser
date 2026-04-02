"""Tests for :class:`Timestamp` mutability and dirty-aware rendering."""

from __future__ import annotations

from datetime import datetime

import pytest

from org_parser.time import Timestamp


def _make_ts(**kwargs: object) -> Timestamp:
    """Construct a minimal active date-only :class:`Timestamp`."""
    defaults: dict[str, object] = {
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


def test_mutating_field_auto_sets_dirty() -> None:
    """Mutating component fields immediately marks timestamp dirty."""
    ts = _make_ts()
    ts.start_year = 2025
    assert ts.dirty is True


def test_constructor_without_raw_generates_clean_render() -> None:
    """Constructing without ``raw`` generates a canonical clean string."""
    ts = Timestamp(is_active=True, start_year=2024, start_month=1, start_day=15)
    assert ts.dirty is False
    assert str(ts) == "<2024-01-15>"


def test_constructor_without_raw_renders_mutations_immediately() -> None:
    """Field mutation is reflected immediately and marks timestamp dirty."""
    ts = Timestamp(is_active=True, start_year=2024, start_month=1, start_day=15)
    ts.start_year = 2030
    assert ts.dirty is True
    assert str(ts) == "<2030-01-15>"


def test_raw_is_private_storage() -> None:
    """The original source text is stored privately, not as ``.raw``."""
    ts = Timestamp(is_active=True, start_year=2024, start_month=1, start_day=15)
    sentinel = object()
    assert getattr(ts, "raw", sentinel) is sentinel


def test_repr_omits_raw_and_none_fields() -> None:
    """Timestamp repr excludes ``raw`` and ``None``-valued fields."""
    ts = _make_ts(
        start_year=2025,
        start_month=12,
        start_day=12,
        start_dayname=None,
    )
    assert repr(ts) == "Timestamp(is_active=True, start_year=2025, start_month=12, start_day=12)"


def test_repr_includes_only_present_optional_fields() -> None:
    """Timestamp repr includes optional fields only when they are present."""
    ts = _make_ts(
        start_year=2025,
        start_month=12,
        start_day=12,
        start_dayname="Fri",
        start_hour=9,
        start_minute=30,
        end_year=2025,
        end_month=12,
        end_day=13,
        end_dayname="Sat",
        end_hour=11,
        end_minute=0,
    )
    assert repr(ts) == (
        "Timestamp(is_active=True, start_year=2025, start_month=12, start_day=12, "
        "start_dayname='Fri', start_hour=9, start_minute=30, end_year=2025, "
        "end_month=12, end_day=13, end_dayname='Sat', end_hour=11, end_minute=0)"
    )


def test_from_source_extracts_repeater_components() -> None:
    """Repeater mark/value/unit components are parsed from source."""
    ts = Timestamp.from_source("<2025-01-06 Mon +1w>")
    assert ts.repeater_mark == "+"
    assert ts.repeater_value == 1
    assert ts.repeater_unit == "w"
    assert ts.repeater_cap_value is None
    assert ts.repeater_cap_unit is None


def test_from_source_extracts_delay_components() -> None:
    """Delay mark/value/unit components are parsed from source."""
    ts = Timestamp.from_source("<2025-01-06 Mon --3d>")
    assert ts.delay_mark == "--"
    assert ts.delay_value == 3
    assert ts.delay_unit == "d"


def test_from_source_extracts_combined_components_regardless_of_order() -> None:
    """Repeater and delay parse correctly even when delay appears first."""
    ts = Timestamp.from_source("<2025-01-06 Mon --2d +1w>")
    assert ts.delay_mark == "--"
    assert ts.delay_value == 2
    assert ts.delay_unit == "d"
    assert ts.repeater_mark == "+"
    assert ts.repeater_value == 1
    assert ts.repeater_unit == "w"


def test_from_source_extracts_repeater_upper_bound_components() -> None:
    """Repeater cap value/unit are parsed from ``+Nunit/Munit`` forms."""
    ts = Timestamp.from_source("<2025-01-06 Mon +1m/3m>")
    assert ts.repeater_mark == "+"
    assert ts.repeater_value == 1
    assert ts.repeater_unit == "m"
    assert ts.repeater_cap_value == 3
    assert ts.repeater_cap_unit == "m"


def test_from_datetime_defaults_to_active_timestamp() -> None:
    """``from_datetime`` creates an active timestamp by default."""
    dt = datetime(2025, 3, 8, 17, 59)
    ts = Timestamp.from_datetime(dt)

    assert ts.is_active is True
    assert ts.start_year == 2025
    assert ts.start_month == 3
    assert ts.start_day == 8
    assert ts.start_dayname == "Sat"
    assert ts.start_hour == 17
    assert ts.start_minute == 59
    assert str(ts) == "<2025-03-08 Sat 17:59>"


def test_from_datetime_accepts_inactive_override() -> None:
    """``from_datetime`` can create inactive timestamp delimiters."""
    dt = datetime(2025, 3, 8, 17, 59)
    ts = Timestamp.from_datetime(dt, is_active=False)
    assert ts.is_active is False
    assert str(ts) == "[2025-03-08 Sat 17:59]"


def test_from_datetime_ignores_seconds_and_microseconds() -> None:
    """Timestamp creation from datetime keeps minute precision only."""
    dt = datetime(2025, 3, 8, 17, 59, 42, 123456)
    ts = Timestamp.from_datetime(dt)
    assert ts.start_hour == 17
    assert ts.start_minute == 59
    assert str(ts) == "<2025-03-08 Sat 17:59>"


# ---------------------------------------------------------------------------
# __str__ — clean path returns raw
# ---------------------------------------------------------------------------


def test_str_clean_returns_raw() -> None:
    """A clean timestamp renders as its original ``raw`` text."""
    raw = "<2024-01-15 Mon>"
    ts = Timestamp.from_source(raw)
    assert str(ts) == raw


def test_str_clean_inactive_returns_raw() -> None:
    """A clean inactive timestamp renders as its original ``raw`` text."""
    raw = "[2024-01-15 Mon]"
    ts = Timestamp.from_source(raw)
    assert str(ts) == raw


# ---------------------------------------------------------------------------
# __str__ — dirty path rebuilds from components
# ---------------------------------------------------------------------------


def test_str_dirty_date_only_active() -> None:
    """Dirty active date-only timestamp renders without time."""
    ts = _make_ts()
    ts.start_year = 2026
    ts.start_month = 3
    ts.start_day = 5
    ts.start_dayname = "Thu"
    assert str(ts) == "<2026-03-05 Thu>"


def test_str_dirty_date_only_inactive() -> None:
    """Dirty inactive date-only timestamp uses ``[...]`` delimiters."""
    ts = _make_ts(is_active=True)
    ts.is_active = False
    assert str(ts) == "[2024-01-15 Mon]"


def test_str_dirty_date_only_no_dayname() -> None:
    """Dirty timestamp without a dayname omits it from output."""
    ts = _make_ts(start_dayname="Mon")
    ts.start_dayname = None
    assert str(ts) == "<2024-01-15>"


def test_str_dirty_with_time() -> None:
    """Dirty timestamp with start time renders ``HH:MM`` component."""
    ts = _make_ts(start_hour=14, start_minute=30)
    ts.start_minute = 31
    ts.start_minute = 30
    assert str(ts) == "<2024-01-15 Mon 14:30>"


def test_str_dirty_with_time_zero_padded() -> None:
    """Hour and minute values are zero-padded to two digits."""
    ts = _make_ts(start_hour=9, start_minute=5)
    ts.start_hour = 10
    ts.start_hour = 9
    assert str(ts) == "<2024-01-15 Mon 09:05>"


def test_str_dirty_same_day_time_range() -> None:
    """Dirty same-day time range renders as ``HH:MM-HH:MM`` within one bracket."""
    ts = _make_ts(
        start_hour=10,
        start_minute=0,
        end_year=2024,
        end_month=1,
        end_day=15,
        end_dayname="Mon",
        end_hour=12,
        end_minute=0,
    )
    ts.end_minute = 1
    ts.end_minute = 0
    assert str(ts) == "<2024-01-15 Mon 10:00-12:00>"


def test_str_dirty_explicit_date_range_active() -> None:
    """Dirty explicit date range renders as ``<start>--<end>``."""
    ts = _make_ts(
        end_year=2024,
        end_month=1,
        end_day=20,
        end_dayname="Sat",
    )
    ts.end_day = 21
    ts.end_day = 20
    assert str(ts) == "<2024-01-15 Mon>--<2024-01-20 Sat>"


def test_str_dirty_explicit_date_range_inactive() -> None:
    """Dirty explicit date range uses ``[...]`` delimiters when inactive."""
    ts = _make_ts(
        is_active=False,
        end_year=2024,
        end_month=1,
        end_day=20,
        end_dayname="Sat",
    )
    ts.end_day = 21
    ts.end_day = 20
    assert str(ts) == "[2024-01-15 Mon]--[2024-01-20 Sat]"


def test_str_dirty_explicit_date_range_with_times() -> None:
    """Dirty explicit date range with times on both ends renders correctly."""
    ts = _make_ts(
        start_hour=9,
        start_minute=0,
        end_year=2024,
        end_month=1,
        end_day=20,
        end_dayname="Sat",
        end_hour=17,
        end_minute=30,
    )
    ts.end_minute = 31
    ts.end_minute = 30
    assert str(ts) == "<2024-01-15 Mon 09:00>--<2024-01-20 Sat 17:30>"


def test_str_dirty_renders_repeater_and_delay_components() -> None:
    """Dirty rendering includes repeater and delay components."""
    ts = _make_ts(
        repeater_mark="+",
        repeater_value=1,
        repeater_unit="w",
        delay_mark="--",
        delay_value=2,
        delay_unit="d",
    )
    ts.start_day = 16
    ts.start_day = 15
    assert str(ts) == "<2024-01-15 Mon +1w --2d>"


def test_str_dirty_renders_repeater_upper_bound_components() -> None:
    """Dirty rendering includes repeater upper-bound components."""
    ts = _make_ts(
        repeater_mark="++",
        repeater_value=1,
        repeater_unit="m",
        repeater_cap_value=3,
        repeater_cap_unit="m",
    )
    ts.start_day = 16
    ts.start_day = 15
    assert str(ts) == "<2024-01-15 Mon ++1m/3m>"


# ---------------------------------------------------------------------------
# Field mutation round-trips
# ---------------------------------------------------------------------------


def test_mutate_year_and_render() -> None:
    """Mutating start_year produces correct output immediately."""
    ts = _make_ts()
    ts.start_year = 2030
    assert str(ts) == "<2030-01-15 Mon>"


def test_mutate_active_flag_and_render() -> None:
    """Flipping is_active changes delimiter style immediately."""
    ts = _make_ts(is_active=True)
    ts.is_active = False
    assert str(ts) == "[2024-01-15 Mon]"


def test_add_time_to_date_only_timestamp() -> None:
    """Adding time components to a date-only timestamp renders the time."""
    ts = _make_ts()
    ts.start_hour = 8
    ts.start_minute = 0
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
        start_dayname="Wed",
        end_year=2024,
        end_month=2,
        end_day=15,
        end_dayname="Thu",
    )
    ts.end_day = 16
    ts.end_day = 15
    assert str(ts) == "<2024-01-15 Wed>--<2024-02-15 Thu>"


def test_str_dirty_cross_year_range_same_day_not_collapsed() -> None:
    """Cross-year range with the same month and day renders as explicit range."""
    ts = _make_ts(
        start_dayname="Mon",
        end_year=2025,
        end_month=1,
        end_day=15,
        end_dayname="Wed",
    )
    ts.end_day = 16
    ts.end_day = 15
    assert str(ts) == "<2024-01-15 Mon>--<2025-01-15 Wed>"


def test_str_dirty_same_day_time_range_still_works_after_fix() -> None:
    """Same-day time range (start/end same date, different times) is unaffected."""
    ts = _make_ts(
        start_hour=9,
        start_minute=0,
        end_year=2024,
        end_month=1,
        end_day=15,
        end_dayname="Mon",
        end_hour=11,
        end_minute=30,
    )
    ts.end_minute = 31
    ts.end_minute = 30
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
def test_str_dirty_date_zero_padding(year: int, month: int, day: int, expected: str) -> None:
    """Year, month, and day are always zero-padded in dirty rendering."""
    ts = _make_ts(start_year=year, start_month=month, start_day=day)
    ts.start_day = day + 1 if day < 31 else day - 1
    ts.start_day = day
    assert str(ts) == expected
