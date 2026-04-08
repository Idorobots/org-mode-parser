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
    assert len(heading.repeats) == 1
    repeat = heading.repeats[0]
    assert isinstance(repeat, Repeat)
    assert repeat.after == "DONE"
    assert repeat.before == "TODO"
    assert str(repeat.timestamp) == "[2026-03-08 Sun 17:59]"
    assert repeat.body == []


def test_repeat_parses_empty_and_missing_states_as_none() -> None:
    """Empty or omitted repeat states are normalized to ``None``."""
    document = loads(
        "* Test\n"
        ":LOGBOOK:\n"
        '- State ""           from              [2025-07-13 Thu 10:32]\n'
        '- State              from ""           [2024-07-13 Thu 10:32]\n'
        "- State              from              [2023-07-13 Thu 10:32]\n"
        '- State ""           from ""           [2023-07-13 Thu 10:32]\n'
        '- State              from "TODO"       [2022-07-10 Sun 22:58]\n'
        '- State ""           from "TODO"       [2021-07-13 Tue 18:53]\n'
        '- State "DONE"       from              [2015-07-09 Tue 22:58]\n'
        '- State "DONE"       from ""           [2013-07-09 Tue 22:58]\n'
        '- State "DONE"       from "TODO"       [2012-07-10 Tue 20:05]\n'
        ":END:\n"
    )

    repeats = document.children[0].repeats
    assert len(repeats) == 9
    assert [(repeat.after, repeat.before) for repeat in repeats] == [
        (None, None),
        (None, None),
        (None, None),
        (None, None),
        (None, "TODO"),
        (None, "TODO"),
        ("DONE", None),
        ("DONE", None),
        ("DONE", "TODO"),
    ]
    assert document.errors == []


def test_repeat_dirty_render_normalizes_none_states_to_empty_quotes() -> None:
    """Dirty repeat rendering serializes missing states as empty quotes."""
    document = loads(
        "* Test\n"
        ":LOGBOOK:\n"
        "- State              from              [2023-07-13 Thu 10:32]\n"
        ":END:\n"
    )

    heading = document.children[0]
    repeat = heading.repeats[0]
    repeat.after = repeat.after
    repeat.before = repeat.before

    rendered = str(heading.logbook)
    assert 'State ""' in rendered
    assert 'from ""' in rendered


def test_repeat_is_completed_uses_document_done_states() -> None:
    """Repeat completion follows owning document done TODO states."""
    document = loads(
        "#+TODO: TODO | DONE\n"
        "* H\n"
        ":LOGBOOK:\n"
        '- State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n'
        ":END:\n"
    )

    repeat = document.children[0].repeats[0]

    assert repeat.is_completed is True


def test_repeat_is_completed_false_when_state_not_in_done_states() -> None:
    """Repeat completion is false when after-state is not a done state."""
    document = loads(
        "#+TODO: TODO | CANCELLED\n"
        "* H\n"
        ":LOGBOOK:\n"
        '- State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n'
        ":END:\n"
    )

    repeat = document.children[0].repeats[0]

    assert repeat.is_completed is False


def test_repeat_is_completed_false_without_parse_backed_document() -> None:
    """Programmatic repeats remain incomplete when detached from parse document."""
    repeat = Repeat(
        after="DONE",
        before="TODO",
        timestamp=Timestamp(
            is_active=False,
            start_year=2026,
            start_month=3,
            start_day=8,
            start_dayname="Sun",
            start_hour=17,
            start_minute=59,
        ),
    )

    assert repeat.is_completed is False


def test_repeat_is_completed_false_when_detached_from_document() -> None:
    """Detached repeats return false when completion context is unknown."""
    repeat = Repeat(
        after="DONE",
        before="TODO",
        timestamp=Timestamp(
            is_active=False,
            start_year=2026,
            start_month=3,
            start_day=8,
        ),
    )

    assert repeat.is_completed is False


def test_repeat_constructor_accepts_raw_string_rich_text_fields() -> None:
    """Repeat constructor accepts raw strings for item tag and first line."""
    repeat = Repeat(
        after="DONE",
        before="TODO",
        timestamp=Timestamp(
            is_active=False,
            start_year=2026,
            start_month=3,
            start_day=8,
        ),
        item_tag="meta",
        first_line='State "DONE" from "TODO" ',
    )

    assert isinstance(repeat.item_tag, RichText)
    assert isinstance(repeat.first_line, RichText)
    assert str(repeat.item_tag) == "meta"


def test_invalid_repeat_with_trailing_chars() -> None:
    """Repeated-task entries with trailing report errors."""
    document = loads(
        "* H\n"
        ":LOGBOOK:\n"
        '- State "CANCELLED"  from "TODO"       [2026-03-08 Sun 13:18] \\\\ foo bar\n'
        "  No need for that with the semantic nodes.\n"
        ":END:\n"
    )

    assert len(document.children[0].repeats) == 0
    assert len(document.errors) == 1
    assert document.errors[0].message == "Invalid repeated-task entry"


def test_repeat_uses_entire_item_body_as_note_payload() -> None:
    """Repeat conversion preserves all continuation body elements as note body."""
    document = loads(
        "* H\n"
        ":LOGBOOK:\n"
        '- State "CANCELLED"  from "TODO"       [2026-03-08 Sun 13:18] \\\\\n'
        "  One note paragraph.\n"
        ":END:\n"
    )

    repeat = document.children[0].repeats[0]
    assert len(repeat.body) == 1
    assert isinstance(repeat.body[0], Paragraph)
    assert str(repeat.body[0]) == "One note paragraph.\n"


def test_repeat_mutation_bubbles_to_list_logbook_and_heading() -> None:
    """Mutating repeat fields marks owning list/logbook/heading dirty."""
    document = loads(
        "* H\n" ":LOGBOOK:\n" '- State "DONE" from "TODO" [2026-03-08 Sun 17:59]\n' ":END:\n"
    )

    heading = document.children[0]
    repeat = heading.repeats[0]

    repeat.after = "CANCELLED"
    repeat.body = [Paragraph(body=RichText("not needed"), parent=repeat)]

    assert repeat.dirty is True
    assert heading.logbook.dirty is True
    assert heading.dirty is True
    assert document.dirty is True
    assert 'State "CANCELLED"' in str(heading.logbook)


def test_repeats_setter_creates_logbook_when_missing() -> None:
    """Assigning repeats populates an initially empty heading logbook."""
    document = loads("* H\nBody\n")
    heading = document.children[0]
    assert len(heading.logbook) == 0

    heading.repeats = [
        Repeat(
            after="DONE",
            before="TODO",
            timestamp=Timestamp(
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
    assert len(heading.repeats) == 1
    assert 'State "DONE"' in str(heading.logbook)


def test_repeats_append_creates_logbook_when_missing() -> None:
    """Adding a task via ``add_repeat`` creates a logbook if absent."""
    document = loads("* H\n")
    heading = document.children[0]

    heading.add_repeat(
        Repeat(
            after="DONE",
            before="TODO",
            timestamp=Timestamp(
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
    assert len(heading.repeats) == 1
    assert len(heading.logbook.repeats) == 1


def test_add_repeat_promotes_existing_body_repeats_into_logbook() -> None:
    """Adding a repeat moves recovered heading-body repeats into the logbook."""
    document = loads("* H\n" '- State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n')
    heading = document.children[0]
    body_repeat = heading.repeats[0]

    heading.add_repeat(
        Repeat(
            after="CANCELLED",
            before="TODO",
            timestamp=Timestamp(
                is_active=False,
                start_year=2026,
                start_month=3,
                start_day=9,
            ),
        )
    )

    assert len(heading.repeats) == 2
    assert len(heading.logbook.repeats) == 2
    assert any(repeat is body_repeat for repeat in heading.logbook.repeats)
    assert heading.body == []


def test_repeats_append_promotes_existing_body_repeats_into_logbook() -> None:
    """Appending to heading repeats moves body repeats into the logbook."""
    document = loads("* H\n" '- State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n')
    heading = document.children[0]
    body_repeat = heading.repeats[0]

    heading.repeats.append(
        Repeat(
            after="CANCELLED",
            before="TODO",
            timestamp=Timestamp(
                is_active=False,
                start_year=2026,
                start_month=3,
                start_day=9,
            ),
        )
    )

    assert len(heading.repeats) == 2
    assert len(heading.logbook.repeats) == 2
    assert any(repeat is body_repeat for repeat in heading.logbook.repeats)
    assert heading.body == []


def test_repeats_setter_clears_body_repeats_and_removes_body_list() -> None:
    """Assigning heading repeats clears pre-existing recovered body repeats."""
    document = loads(
        "* DONE Test\n"
        '   - State "DONE"       from "ACTIVE"     [2012-10-05 pią 19:49]\n'
        '   - State "ACTIVE"     from "BLOCKER"    [2012-10-03 śro 09:37]\n'
        '   - State "BLOCKER"    from "BLOCKER"    [2012-09-19 śro 17:55]\n'
    )
    heading = document.children[0]

    heading.repeats = []

    assert heading.repeats == []
    assert heading.logbook.repeats == []
    assert heading.body == []
    assert str(heading) == "* DONE Test\n"


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
    assert heading.clock_entries == heading.logbook.clock_entries


def test_heading_clock_setter_creates_logbook_when_missing() -> None:
    """Assigning heading clocks populates an initially empty logbook."""
    document = loads("* H\nBody\n")
    heading = document.children[0]
    assert len(heading.logbook) == 0

    clock = Clock(
        timestamp=Timestamp(
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


def test_clock_entries_append_promotes_existing_body_clocks_into_logbook() -> None:
    """Appending heading clocks moves recovered body clocks into the logbook."""
    document = loads(
        "* H\n" "\n" "  CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
    )
    heading = document.children[0]
    body_clock = heading.clock_entries[0]

    heading.clock_entries.append(
        Clock(
            timestamp=Timestamp(
                is_active=False,
                start_year=2026,
                start_month=1,
                start_day=1,
            ),
            duration="0:10",
        )
    )

    assert len(heading.clock_entries) == 2
    assert len(heading.logbook.clock_entries) == 2
    assert any(clock is body_clock for clock in heading.logbook.clock_entries)
    assert all("CLOCK:" not in str(element) for element in heading.body)


def test_clock_entries_setter_clears_body_clocks() -> None:
    """Assigning heading clocks removes recovered body clocks from body."""
    document = loads(
        "* H\n" "\n" "CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
    )
    heading = document.children[0]

    heading.clock_entries = []

    assert heading.clock_entries == []
    assert heading.logbook.clock_entries == []
    assert all("CLOCK:" not in str(element) for element in heading.body)
    assert "CLOCK:" not in str(heading)


def test_repeats_mutation_promotes_indented_body_repeats_and_clocks() -> None:
    """Mutating heading repeats promotes indented body repeats and clocks."""
    document = loads(
        "* H\n"
        '  - State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n'
        "  CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
    )
    heading = document.children[0]
    body_repeat = heading.repeats[0]
    body_clock = heading.clock_entries[0]

    heading.repeats.append(
        Repeat(
            after="CANCELLED",
            before="TODO",
            timestamp=Timestamp(
                is_active=False,
                start_year=2026,
                start_month=3,
                start_day=9,
            ),
        )
    )

    assert len(heading.repeats) == 2
    assert len(heading.clock_entries) == 1
    assert len(heading.logbook.repeats) == 2
    assert len(heading.logbook.clock_entries) == 1
    assert any(repeat is body_repeat for repeat in heading.logbook.repeats)
    assert any(clock is body_clock for clock in heading.logbook.clock_entries)
    assert heading.body == []


def test_clock_entries_mutation_promotes_indented_logbook_repeats_and_clocks() -> None:
    """Mutating heading clocks promotes indented LOGBOOK repeats and clocks."""
    document = loads(
        "* H\n"
        "    :LOGBOOK:\n"
        '    - State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n'
        "    CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
        "    :END:\n"
    )
    heading = document.children[0]
    body_repeat = heading.repeats[0]
    body_clock = heading.clock_entries[0]

    heading.clock_entries.append(
        Clock(
            timestamp=Timestamp(
                is_active=False,
                start_year=2026,
                start_month=1,
                start_day=1,
            ),
            duration="0:10",
        )
    )

    assert len(heading.repeats) == 1
    assert len(heading.clock_entries) == 2
    assert len(heading.logbook.repeats) == 1
    assert len(heading.logbook.clock_entries) == 2
    assert any(repeat is body_repeat for repeat in heading.logbook.repeats)
    assert any(clock is body_clock for clock in heading.logbook.clock_entries)
    assert heading.body == []


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
    assert heading.repeats == [parsed.items[0]]


def test_heading_body_repeat_recovery_sets_document_for_completion() -> None:
    """Recovered body repeats attach owning document for completion checks."""
    document = loads(
        "#+TODO: TODO | DONE\n"
        "* H\n"
        '- State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n'
    )

    repeat = document.children[0].repeats[0]

    assert repeat.is_completed is True


def test_heading_body_recovery_attaches_document_for_existing_repeat_items() -> None:
    """Recovery stamps document onto pre-existing Repeat items in heading lists."""
    document = loads("#+TODO: TODO | DONE\n* H\n")
    heading = document.children[0]
    repeat = Repeat(
        after="DONE",
        before="TODO",
        timestamp=Timestamp(
            is_active=False,
            start_year=2026,
            start_month=3,
            start_day=8,
        ),
    )

    heading.body = [List(items=[repeat])]

    assert heading.repeats == [repeat]
    assert repeat.is_completed is True


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
    assert heading.repeats == []


def test_heading_clock_cache_extracts_non_indented_body_clock_entries() -> None:
    """Bare heading-body clocks are extracted into heading clock cache."""
    document = loads(
        "* H\n" "\n" "CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 10:30] =>  1:30\n"
    )

    heading = document.children[0]
    assert len(heading.clock_entries) == 1
    assert isinstance(heading.clock_entries[0], Clock)


def test_heading_clock_cache_extracts_indented_body_clock_entries() -> None:
    """Heading clock cache includes clocks nested inside indent blocks."""
    document = loads(
        "* H\n" "\n" "  CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
    )

    heading = document.children[0]
    assert len(heading.clock_entries) == 1
    assert isinstance(heading.clock_entries[0], Clock)


def test_heading_cache_ignores_repeats_and_clocks_inside_custom_drawers() -> None:
    """Custom drawer repeats/clocks stay in-place and are excluded from caches."""
    document = loads(
        "* H\n"
        ":NOTE:\n"
        '- State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n'
        "CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
        ":END:\n"
    )
    heading = document.children[0]

    heading.repeats.append(
        Repeat(
            after="CANCELLED",
            before="TODO",
            timestamp=Timestamp(
                is_active=False,
                start_year=2026,
                start_month=3,
                start_day=9,
            ),
        )
    )
    heading.clock_entries.append(
        Clock(
            timestamp=Timestamp(
                is_active=False,
                start_year=2026,
                start_month=1,
                start_day=1,
            ),
            duration="0:10",
        )
    )

    assert len(heading.repeats) == 1
    assert len(heading.logbook.repeats) == 1
    assert len(heading.clock_entries) == 1
    assert len(heading.logbook.clock_entries) == 1
    assert any('State "DONE"' in str(element) for element in heading.body)
    assert any("CLOCK:" in str(element) for element in heading.body)


def test_heading_cache_includes_indented_logbook_entries() -> None:
    """Indented LOGBOOK drawers still contribute repeats and clock entries."""
    document = loads(
        "* H\n"
        "    :LOGBOOK:\n"
        '    - State "DONE"       from "TODO"       [2026-03-08 Sun 17:59]\n'
        "    CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
        "    :END:\n"
    )
    heading = document.children[0]

    assert len(heading.repeats) == 1
    assert len(heading.clock_entries) == 1
    assert heading.repeats[0].after == "DONE"
    assert heading.repeats[0].before == "TODO"


def test_heading_clock_cache_ignores_clocks_in_nested_list_bodies() -> None:
    """Only top-level lists contribute clock extraction for heading cache."""
    document = loads(
        "* H\n" "- parent\n" "  CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
    )

    heading = document.children[0]
    assert heading.clock_entries == []
