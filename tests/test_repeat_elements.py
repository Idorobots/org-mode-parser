"""Tests for repeated-task semantic entries in logbooks."""

from __future__ import annotations

from org_parser import loads
from org_parser.element import List, Logbook, Paragraph, Repeat
from org_parser.text import RichText
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
        "* H\n"
        ":LOGBOOK:\n"
        '- State "DONE" from "TODO" [2026-03-08 Sun 17:59]\n'
        ":END:\n"
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
        "* H\n"
        ":LOGBOOK:\n"
        '- [X] State "DONE" from "TODO" [2026-03-08 Sun 17:59]\n'
        ":END:\n"
    )
    heading = document.children[0]
    assert heading.logbook is not None
    assert heading.logbook.repeats == []
    assert isinstance(heading.logbook.body[0], List)
    assert isinstance(heading.logbook.body[0].items[0], Repeat) is False
