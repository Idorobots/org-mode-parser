"""Tests for repeated-task semantic entries in logbooks."""

from __future__ import annotations

from org_parser import loads
from org_parser.element import List, Logbook, Repeat
from org_parser.time import Timestamp


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
    assert repeat.note is None


def test_repeat_parses_logbook_item_with_note_line() -> None:
    """Repeated-task entries with escaped line break expose note text."""
    document = loads(
        "* H\n"
        ":LOGBOOK:\n"
        '- State "CANCELLED"  from "TODO"       [2026-03-08 Sun 13:18] \\\\n'
        "  No need for that with the semantic nodes.\n"
        ":END:\n"
    )

    repeat = document.children[0].repeated_tasks[0]
    assert repeat.after == "CANCELLED"
    assert repeat.before == "TODO"
    assert str(repeat.timestamp) == "[2026-03-08 Sun 13:18]"
    assert repeat.note == "No need for that with the semantic nodes."


def test_repeat_mutation_bubbles_to_list_logbook_and_heading() -> None:
    """Mutating repeat fields marks owning list/logbook/heading dirty."""
    document = loads(
        "* H\n"
        ":LOGBOOK:\n"
        '- State "DONE" from "TODO" [2026-03-08 Sun 17:59]\n'
        ":END:\n"
    )

    heading = document.children[0]
    assert heading.logbook is not None
    repeat = heading.repeated_tasks[0]

    repeat.after = "CANCELLED"
    repeat.note = "not needed"

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
    """Appending via ``repeated_tasks`` creates a heading logbook if absent."""
    document = loads("* H\n")
    heading = document.children[0]

    heading.repeated_tasks.append(
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


def test_non_logbook_lists_do_not_convert_items_to_repeats() -> None:
    """Only logbook lists are interpreted as repeated-task entries."""
    document = loads('- State "DONE" from "TODO" [2026-03-08 Sun 17:59]\n')
    assert isinstance(document.body[0], List)
    plain_list = document.body[0]
    item = plain_list.items[0]
    assert isinstance(item, Repeat) is False
