"""Tests for repeated-task semantic entries in logbooks."""

from __future__ import annotations

from org_parser import loads
from org_parser.element import List, Logbook, Paragraph, Repeat
from org_parser.text import RichText
from org_parser.time import Clock, Timestamp


def test_repeat_parses_logbook_item_without_note() -> None:
    """Simple repeated-task entries parse into :class:`Repeat` values."""
    document = loads(
        "* H\n"
        ":LOGBOOK:\n"
        '- State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n'
        ":END:\n"
    )

    heading = document.children[0]
    assert heading.logbook is not None
    assert len(heading.repeated_tasks) == 1
    repeat = heading.repeated_tasks[0]
    assert isinstance(repeat, Repeat)
    assert repeat.after == "DONE"
    assert repeat.before == "TODO"
    assert str(repeat.timestamp) == "[2026-03-08 Sun 17:59]"
    assert repeat.body == []


def test_invalid_repeat_with_trailing_chars() -> None:
    """Repeated-task entries with trailing report errors."""
    document = loads(
        "* H\n"
        ":LOGBOOK:\n"
        '- State "CANCELLED"  from "TODO"       [2026-03-08 Sun 13:18] \\\\ foo bar\n'
        "  No need for that with the semantic nodes.\n"
        ":END:\n"
    )

    assert len(document.children[0].repeated_tasks) == 0
    assert len(document.errors) == 1


def test_repeat_uses_entire_item_body_as_note_payload() -> None:
    """Repeat conversion preserves all continuation body elements as note body."""
    document = loads(
        "* H\n"
        ":LOGBOOK:\n"
        '- State "CANCELLED"  from "TODO"       [2026-03-08 Sun 13:18] \\\\\n'
        "  One note paragraph.\n"
        ":END:\n"
    )

    repeat = document.children[0].repeated_tasks[0]
    assert len(repeat.body) == 1
    assert isinstance(repeat.body[0], Paragraph)
    assert str(repeat.body[0]) == "One note paragraph.\n"


def test_repeat_mutation_bubbles_to_list_logbook_and_heading() -> None:
    """Mutating repeat fields marks owning list/logbook/heading dirty."""
    document = loads(
        "* H\n" ":LOGBOOK:\n" '- State "DONE" from "TODO" [2026-03-08 Sun 17:59]\n' ":END:\n"
    )

    heading = document.children[0]
    assert heading.logbook is not None
    repeat = heading.repeated_tasks[0]

    repeat.after = "CANCELLED"
    repeat.body = [Paragraph(body=RichText("not needed"), parent=repeat)]

    assert repeat.dirty is True
    assert heading.logbook.dirty is True
    assert heading.dirty is True
    assert document.dirty is True
    assert 'State "CANCELLED"' in str(heading.logbook)


def test_repeated_tasks_setter_creates_logbook_when_missing() -> None:
    """Assigning repeated tasks creates a heading logbook when absent."""
    document = loads("* H\nBody\n")
    heading = document.children[0]
    assert heading.logbook is None

    heading.repeated_tasks = [
        Repeat(
            after="DONE",
            before="TODO",
            timestamp=Timestamp(
                raw="[2026-03-08 Sun 17:59]",
                is_active=False,
                start_year=2026,
                start_month=3,
                start_day=8,
                start_dayname="Sun",
                start_hour=17,
                start_minute=59,
            ),
        )
    ]

    assert isinstance(heading.logbook, Logbook)
    assert len(heading.logbook.repeats) == 1
    assert len(heading.repeated_tasks) == 1
    assert 'State "DONE"' in str(heading.logbook)


def test_repeated_tasks_append_creates_logbook_when_missing() -> None:
    """Adding a task via ``add_repeated_task`` creates a logbook if absent."""
    document = loads("* H\n")
    heading = document.children[0]

    heading.add_repeated_task(
        Repeat(
            after="DONE",
            before="TODO",
            timestamp=Timestamp(
                raw="[2026-03-08 Sun 17:59]",
                is_active=False,
                start_year=2026,
                start_month=3,
                start_day=8,
                start_dayname="Sun",
                start_hour=17,
                start_minute=59,
            ),
        )
    )

    assert isinstance(heading.logbook, Logbook)
    assert len(heading.repeated_tasks) == 1
    assert len(heading.logbook.repeats) == 1


def test_heading_clock_cache_extracts_logbook_clock_entries() -> None:
    """Heading exposes cached ``CLOCK`` entries extracted from ``LOGBOOK``."""
    document = loads(
        "* H\n"
        ":LOGBOOK:\n"
        "CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 10:30] =>  1:30\n"
        ":END:\n"
    )

    heading = document.children[0]
    assert len(heading.clock_entries) == 1
    assert isinstance(heading.clock_entries[0], Clock)
    assert heading.logbook is not None
    assert heading.clock_entries is heading.logbook.clock_entries


def test_heading_clock_setter_creates_logbook_when_missing() -> None:
    """Assigning heading clocks creates logbook and syncs body/cache objects."""
    document = loads("* H\nBody\n")
    heading = document.children[0]
    assert heading.logbook is None

    clock = Clock(
        timestamp=Timestamp(
            raw="[2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30]",
            is_active=False,
            start_year=2025,
            start_month=1,
            start_day=8,
            start_dayname="Wed",
            start_hour=9,
            start_minute=0,
            end_year=2025,
            end_month=1,
            end_day=8,
            end_dayname="Wed",
            end_hour=9,
            end_minute=30,
        ),
        duration="0:30",
    )
    heading.clock_entries = [clock]

    assert isinstance(heading.logbook, Logbook)
    assert heading.clock_entries == [clock]
    assert heading.logbook.clock_entries == [clock]
    assert heading.logbook.body == [clock]
    assert heading.logbook.body[0] is heading.clock_entries[0]


def test_non_logbook_lists_do_not_convert_items_to_repeats() -> None:
    """Only logbook lists are interpreted as repeated-task entries."""
    document = loads('- State "DONE" from "TODO" [2026-03-08 Sun 17:59]\n')
    assert isinstance(document.body[0], List)
    plain_list = document.body[0]
    item = plain_list.items[0]
    assert isinstance(item, Repeat) is False


def test_repeat_parse_requires_plain_item_shape() -> None:
    """Items with checkbox/counter metadata are not converted to repeats."""
    document = loads(
        "* H\n" ":LOGBOOK:\n" '- [X] State "DONE" from "TODO" [2026-03-08 Sun 17:59]\n' ":END:\n"
    )
    heading = document.children[0]
    assert heading.logbook is not None
    assert heading.logbook.repeats == []
    assert isinstance(heading.logbook.body[0], List)
    assert isinstance(heading.logbook.body[0].items[0], Repeat) is False


def test_heading_body_lists_are_recovered_for_repeats() -> None:
    """Heading body list items that match repeat syntax are recovered."""
    document = loads("* H\n" '- State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n')

    heading = document.children[0]
    assert isinstance(heading.body[0], List)
    parsed = heading.body[0]
    assert isinstance(parsed.items[0], Repeat)
    assert heading.repeated_tasks == [parsed.items[0]]


def test_heading_body_nested_lists_are_not_recovered_for_repeats() -> None:
    """Only top-level heading body lists are scanned for repeat recovery."""
    document = loads(
        "* H\n" "- parent\n" '  - State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n'
    )

    heading = document.children[0]
    assert isinstance(heading.body[0], List)
    outer = heading.body[0]
    assert len(outer.items) == 1
    assert len(outer.items[0].body) == 1
    assert isinstance(outer.items[0].body[0], List)
    nested = outer.items[0].body[0]
    assert isinstance(nested.items[0], Repeat) is False
    assert heading.repeated_tasks == []


def test_heading_clock_cache_ignores_non_drawer_body_clock_entries() -> None:
    """Bare heading-body clocks are ignored by the explicit recovery scan."""
    document = loads(
        "* H\n" "\n" "CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 10:30] =>  1:30\n"
    )

    heading = document.children[0]
    assert heading.clock_entries == []
    assert heading.logbook is None


def test_heading_clock_cache_extracts_nested_body_clock_entries() -> None:
    """Heading clock cache includes clocks nested inside body containers."""
    document = loads(
        "* H\n"
        ":NOTE:\n"
        ":INNER:\n"
        "CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
        ":END:\n"
        ":END:\n"
    )

    heading = document.children[0]
    assert len(heading.clock_entries) == 1
    assert isinstance(heading.clock_entries[0], Clock)


def test_heading_clock_cache_ignores_clocks_in_nested_list_bodies() -> None:
    """Only top-level lists contribute clock extraction for heading cache."""
    document = loads(
        "* H\n" "- parent\n" "  CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
    )

    heading = document.children[0]
    assert heading.clock_entries == []
