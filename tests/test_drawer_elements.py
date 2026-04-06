"""Tests for drawer semantic element abstractions."""

from __future__ import annotations

from org_parser import loads
from org_parser.element import Drawer, List, Logbook, Paragraph, Properties, Repeat
from org_parser.text import RichText
from org_parser.time import Clock, Timestamp


def test_property_drawer_parses_to_properties_mapping() -> None:
    """Property drawers are parsed to dictionary-like ``Properties`` objects."""
    document = loads(":PROPERTIES:\n:ID: alpha\n:CATEGORY: work\n:END:\n")

    assert isinstance(document.properties, Properties)
    properties = document.properties
    assert properties is not None
    assert isinstance(properties, Properties)
    assert str(properties["ID"]) == "alpha"
    assert str(properties["CATEGORY"]) == "work"


def test_properties_support_last_one_wins() -> None:
    """Duplicate property keys keep the value from the last entry."""
    document = loads(":PROPERTIES:\n:ID: old\n:ID: new\n:END:\n")

    assert isinstance(document.properties, Properties)
    properties = document.properties
    assert properties is not None
    assert str(properties["ID"]) == "new"


def test_properties_are_mutable_and_dirty_on_set() -> None:
    """Setting one property value marks owning structures as dirty."""
    document = loads(":PROPERTIES:\n:ID: alpha\n:END:\n")

    assert isinstance(document.properties, Properties)
    properties = document.properties
    assert properties is not None
    assert properties.dirty is False
    assert document.dirty is False

    properties["ID"] = RichText("beta")

    assert str(properties["ID"]) == "beta"
    assert properties.dirty is True
    assert document.dirty is True
    assert str(properties) == ":PROPERTIES:\n:ID: beta\n:END:\n"


def test_properties_constructor_preserves_assigned_value_types() -> None:
    """Constructor stores mapping values as-is and adopts rich-text values."""
    properties = Properties(properties={"ID": "alpha", "CATEGORY": RichText("work")})

    assert isinstance(properties["ID"], str)
    category = properties["CATEGORY"]
    assert isinstance(category, RichText)
    assert properties["ID"] == "alpha"
    assert str(category) == "work"
    assert category.parent is properties


def test_properties_support_arbitrary_values_and_stringify_for_rendering() -> None:
    """Non-rich property values remain typed and stringify in drawer output."""
    properties = Properties()

    properties["foo"] = 23

    count = properties["foo"]
    assert count == 23
    assert isinstance(count, int)
    assert count * 2 == 46
    assert str(properties) == ":PROPERTIES:\n:foo: 23\n:END:\n"


def test_properties_value_mutation_bubbles_to_drawer_and_document() -> None:
    """Mutating one owned rich-text value updates rendered drawer output."""
    document = loads(":PROPERTIES:\n:NAME: old\n:END:\n")

    assert isinstance(document.properties, Properties)
    properties = document.properties
    assert properties is not None

    name = properties["NAME"]
    assert isinstance(name, RichText)
    name.text = "new"

    assert properties.dirty is True
    assert document.dirty is True
    assert str(properties) == ":PROPERTIES:\n:NAME: new\n:END:\n"


def test_heading_properties_drawer_is_exposed_in_heading_body() -> None:
    """Heading-level property drawer is exposed via dedicated field."""
    document = loads("* H\n:PROPERTIES:\n:ID: abc\n:END:\n")

    assert isinstance(document.children[0].properties, Properties)
    assert str(document.children[0].properties["ID"]) == "abc"
    assert document.children[0].body == []


def test_generic_drawer_parses_name_and_body() -> None:
    """Custom drawers are represented as ``Drawer`` elements."""
    document = loads(":NOTE:\nSome notes.\n:END:\n")

    assert isinstance(document.body[0], Drawer)
    drawer = document.body[0]
    assert drawer.name == "NOTE"
    assert len(drawer.body) == 1


def test_unterminated_drawer_reports_document_error() -> None:
    """Truncated drawers report one parse error on the document."""
    document = loads("* hurr\n:hurr:\ndurr\n* derp\n")

    assert len(document.children) == 2
    assert len(document.errors) == 1
    assert document.errors[0].message == "Unterminated drawer (missing :END: marker)"


def test_drawer_marker_trailing_start_text_reports_specific_message() -> None:
    """Trailing text on a drawer start marker reports a drawer-marker error."""
    document = loads(":NOTE: x\nSome notes.\n:END:\n")

    assert len(document.errors) == 1
    assert document.errors[0].text == " x"
    assert document.errors[0].message == "Trailing characters in drawer marker"


def test_drawer_marker_trailing_end_text_reports_specific_message() -> None:
    """Trailing text on a drawer end marker reports a drawer-marker error."""
    document = loads(":NOTE:\nSome notes.\n:END: x\n")

    assert len(document.errors) == 1
    assert document.errors[0].text == " x"
    assert document.errors[0].message == "Trailing characters in drawer marker"


def test_property_drawer_end_marker_trailing_text_reports_specific_message() -> None:
    """Property drawer end-marker trailing text reports a drawer-marker error."""
    document = loads(":PROPERTIES:\n:ID: alpha\n:END: x\n")

    assert len(document.errors) == 1
    assert document.errors[0].text == " x"
    assert document.errors[0].message == "Trailing characters in drawer marker"


def test_logbook_drawer_end_marker_trailing_text_reports_specific_message() -> None:
    """Logbook drawer end-marker trailing text reports a drawer-marker error."""
    document = loads(":LOGBOOK:\nCLOCK: [2025-01-08 Wed 09:00]\n:END: x\n")

    assert len(document.errors) == 1
    assert document.errors[0].text == " x"
    assert document.errors[0].message == "Trailing characters in drawer marker"


def test_logbook_drawer_extracts_clocks_and_repeats() -> None:
    """Logbook drawers separate clock entries from repeat entries."""
    document = loads(
        "* H\n"
        ":LOGBOOK:\n"
        '- State "DONE"       from "TODO"       [2025-01-08 Wed 09:00]\n'
        "CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 10:30] =>  1:30\n"
        "CLOCK: [2025-01-09 Thu 09:00]--[2025-01-09 Thu 10:00] =>  1:00\n"
        ":END:\n"
    )

    assert isinstance(document.children[0].logbook, Logbook)
    logbook = document.children[0].logbook
    assert len(logbook.clock_entries) == 2
    assert all(isinstance(entry, Clock) for entry in logbook.clock_entries)
    assert len(logbook.repeats) == 1
    assert isinstance(logbook.repeats[0], Repeat)
    assert logbook.repeats[0].after == "DONE"
    assert logbook.repeats[0].before == "TODO"
    assert isinstance(logbook.repeats[0].parent, List)
    assert all(entry.parent is logbook for entry in logbook.clock_entries)
    assert any(element is logbook.clock_entries[0] for element in logbook.body)
    assert any(element is logbook.clock_entries[1] for element in logbook.body)
    repeat_items = [
        item
        for element in logbook.body
        if isinstance(element, List)
        for item in element.items
        if isinstance(item, Repeat)
    ]
    assert repeat_items == [logbook.repeats[0]]
    assert document.children[0].body == []


def test_logbook_setters_keep_body_and_extracted_entries_identical() -> None:
    """Assigned clocks/repeats are the same objects that appear in body."""
    document = loads("* H\n")
    heading = document.children[0]

    clock = Clock(duration="0:30")
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

    logbook = Logbook(parent=heading)
    logbook.clock_entries = [clock]
    logbook.repeats = [repeat]

    assert logbook.clock_entries[0] is clock
    assert any(element is clock for element in logbook.body)
    repeat_items = [
        item
        for element in logbook.body
        if isinstance(element, List)
        for item in element.items
        if isinstance(item, Repeat)
    ]
    assert repeat_items == [repeat]
    assert repeat_items[0] is logbook.repeats[0]


def test_document_merges_multiple_properties_and_logbooks() -> None:
    """Multiple dedicated drawers merge into one per drawer type."""
    document = loads(
        ":PROPERTIES:\n:ID: one\n:END:\n"
        ":PROPERTIES:\n:ID: two\n:CATEGORY: work\n:END:\n"
        ":LOGBOOK:\n"
        "CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
        ":END:\n"
        ":LOGBOOK:\n"
        "CLOCK: [2025-01-08 Wed 10:00]--[2025-01-08 Wed 11:00] =>  1:00\n"
        ":END:\n"
    )

    assert isinstance(document.properties, Properties)
    assert str(document.properties["ID"]) == "two"
    assert str(document.properties["CATEGORY"]) == "work"
    assert isinstance(document.logbook, Logbook)
    assert len(document.logbook.clock_entries) == 2
    assert document.body == []


def test_heading_merges_multiple_properties_and_logbooks() -> None:
    """Heading-level dedicated drawers are merged by drawer type."""
    document = loads(
        "* H\n"
        ":PROPERTIES:\n:ID: one\n:END:\n"
        ":LOGBOOK:\n"
        "CLOCK: [2025-01-08 Wed 09:00]--[2025-01-08 Wed 09:30] =>  0:30\n"
        ":END:\n"
        ":PROPERTIES:\n:ID: two\n:END:\n"
        ":LOGBOOK:\n"
        "CLOCK: [2025-01-08 Wed 10:00]--[2025-01-08 Wed 11:00] =>  1:00\n"
        ":END:\n"
        ":NOTE:\nkept in body\n:END:\n"
    )

    heading = document.children[0]
    assert isinstance(heading.properties, Properties)
    assert str(heading.properties["ID"]) == "two"
    assert isinstance(heading.logbook, Logbook)
    assert len(heading.logbook.clock_entries) == 2
    assert len(heading.body) == 1
    assert isinstance(heading.body[0], Drawer)


def test_dirty_heading_drawer_order_is_properties_then_logbook() -> None:
    """Dirty heading rendering prints properties before logbook drawers."""
    document = loads("* H\nBody\n")
    heading = document.children[0]
    heading.properties = Properties(properties={"ID": RichText("abc")})
    heading.logbook = Logbook(
        clock_entries=[Clock(duration="0:30")],
    )

    rendered = str(heading)
    assert rendered.index(":PROPERTIES:") < rendered.index(":LOGBOOK:")


def test_heading_properties_setter_accepts_dictionary_values() -> None:
    """Heading properties setter stores dictionary values without coercion."""
    document = loads("* H\n")
    heading = document.children[0]

    heading.properties = {"ID": "abc", "CATEGORY": RichText("work")}

    assert isinstance(heading.properties, Properties)
    assert heading.properties["ID"] == "abc"
    assert isinstance(heading.properties["ID"], str)
    heading_category = heading.properties["CATEGORY"]
    assert isinstance(heading_category, RichText)
    assert str(heading_category) == "work"
    assert heading_category.parent is heading.properties


def test_dirty_document_drawer_order_is_properties_then_logbook() -> None:
    """Dirty document rendering prints properties before logbook drawers."""
    document = loads("Text\n")
    document.properties = Properties(properties={"ID": RichText("abc")})
    document.logbook = Logbook(
        clock_entries=[Clock(duration="0:30")],
    )

    rendered = str(document)
    assert rendered.index(":PROPERTIES:") < rendered.index(":LOGBOOK:")


def test_document_properties_setter_accepts_dictionary_values() -> None:
    """Document properties setter stores dictionary values without coercion."""
    document = loads("Text\n")

    document.properties = {"ID": "abc", "CATEGORY": RichText("work")}

    assert isinstance(document.properties, Properties)
    assert document.properties["ID"] == "abc"
    assert isinstance(document.properties["ID"], str)
    document_category = document.properties["CATEGORY"]
    assert isinstance(document_category, RichText)
    assert str(document_category) == "work"
    assert document_category.parent is document.properties


def test_dirty_document_omits_empty_default_drawers() -> None:
    """Dirty document rendering omits empty default dedicated drawers."""
    document = loads("#+TITLE: T\n")

    document.filename = "renamed.org"

    assert str(document) == "#+TITLE: T\n"


def test_dirty_document_renders_newline_between_keyword_and_logbook() -> None:
    """Dirty document rendering separates keyword and logbook lines."""
    document = loads("#+TITLE: Logbook")
    document.logbook = Logbook()
    document.logbook.clock_entries = [Clock.from_source("CLOCK: [2025-10-10]")]

    assert str(document) == ("#+TITLE: Logbook\n" ":LOGBOOK:\n" "CLOCK: [2025-10-10]\n" ":END:\n")


def test_dirty_heading_render_separates_body_and_child_heading() -> None:
    """Dirty heading render keeps child heading on a new line."""
    document = loads("* H\nBody")
    heading = document.children[0]
    child = loads("* Child").children[0]

    heading.children = [child]

    assert heading.render() == "* H\nBody\n** Child\n"


def test_dirty_heading_omits_empty_default_drawers() -> None:
    """Dirty heading rendering omits empty default dedicated drawers."""
    document = loads("* H\n")
    heading = document.children[0]

    heading.todo = "TODO"

    assert str(heading) == "* TODO H\n"


def test_drawer_body_setter_marks_dirty() -> None:
    """Replacing drawer body marks drawer and document as dirty."""
    document = loads(":NOTE:\nA\n:END:\n")

    assert isinstance(document.body[0], Drawer)
    drawer = document.body[0]
    assert drawer.dirty is False
    assert document.dirty is False

    drawer.body = []

    assert drawer.dirty is True
    assert document.dirty is True
    assert str(drawer) == ":NOTE:\n:END:\n"


def test_drawer_body_setter_accepts_element_and_raw_string() -> None:
    """Drawer body setter accepts one element and raw string input."""
    document = loads(":NOTE:\nA\n:END:\n")

    assert isinstance(document.body[0], Drawer)
    drawer = document.body[0]
    paragraph = Paragraph(body=RichText("Two\n"))

    drawer.body = paragraph

    assert drawer.body == [paragraph]
    assert drawer.body[0].parent is drawer

    drawer.body = "raw"

    assert len(drawer.body) == 1
    assert isinstance(drawer.body[0], Paragraph)
    assert str(drawer.body[0]) == "raw"
    assert drawer.body[0].parent is drawer
    assert str(drawer) == ":NOTE:\nraw\n:END:\n"


def test_logbook_body_setter_accepts_element_and_raw_string() -> None:
    """Logbook body setter accepts one element and raw string input."""
    document = loads("* H\n")
    logbook = document.children[0].logbook
    clock = Clock(duration="0:15")

    logbook.body = clock

    assert logbook.body == [clock]
    assert logbook.clock_entries == [clock]
    assert logbook.repeats == []
    assert clock.parent is logbook

    logbook.body = "plain"

    assert len(logbook.body) == 1
    assert isinstance(logbook.body[0], Paragraph)
    assert str(logbook.body[0]) == "plain"
    assert logbook.body[0].parent is logbook
    assert logbook.clock_entries == []
    assert logbook.repeats == []


def test_drawer_and_logbook_list_appends_mark_dirty() -> None:
    """Appending to drawer/logbook list fields marks owner dirty."""
    drawer_document = loads(":NOTE:\nA\n:END:\n")
    assert isinstance(drawer_document.body[0], Drawer)
    drawer = drawer_document.body[0]
    paragraph = Paragraph(body=RichText("B\n"))
    drawer.body.append(paragraph)
    assert drawer.dirty is True
    assert drawer_document.dirty is True
    assert paragraph.parent is drawer

    logbook_document = loads("* H\n")
    logbook = logbook_document.children[0].logbook
    clock = Clock(duration="0:10")
    logbook.clock_entries.append(clock)
    assert logbook.dirty is True
    assert logbook_document.dirty is True
    assert clock.parent is logbook
