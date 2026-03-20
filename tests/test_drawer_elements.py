"""Tests for drawer semantic element abstractions."""

from __future__ import annotations

from org_parser import loads
from org_parser.element import Drawer, List, Logbook, Properties, Repeat
from org_parser.text import RichText
from org_parser.time import Clock


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


def test_properties_value_mutation_bubbles_to_drawer_and_document() -> None:
    """Mutating one owned rich-text value updates rendered drawer output."""
    document = loads(":PROPERTIES:\n:NAME: old\n:END:\n")

    assert isinstance(document.properties, Properties)
    properties = document.properties
    assert properties is not None

    properties["NAME"].text = "new"

    assert properties.dirty is True
    assert document.dirty is True
    assert str(properties) == ":PROPERTIES:\n:NAME: new\n:END:\n"


def test_heading_properties_drawer_is_exposed_in_heading_body() -> None:
    """Heading-level property drawer is exposed via dedicated field."""
    document = loads("* H\n:PROPERTIES:\n:ID: abc\n:END:\n")

    assert isinstance(document.children[0].properties, Properties)
    assert document.children[0].properties is not None
    assert str(document.children[0].properties["ID"]) == "abc"
    assert document.children[0].body == []


def test_generic_drawer_parses_name_and_body() -> None:
    """Custom drawers are represented as ``Drawer`` elements."""
    document = loads(":NOTE:\nSome notes.\n:END:\n")

    assert isinstance(document.body[0], Drawer)
    drawer = document.body[0]
    assert drawer.name == "NOTE"
    assert len(drawer.body) == 1


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
    assert logbook is not None
    assert len(logbook.clock_entries) == 2
    assert all(isinstance(entry, Clock) for entry in logbook.clock_entries)
    assert len(logbook.repeats) == 1
    assert isinstance(logbook.repeats[0], Repeat)
    assert logbook.repeats[0].after == "DONE"
    assert logbook.repeats[0].before == "TODO"
    assert isinstance(logbook.repeats[0].parent, List)
    assert all(entry.parent is logbook for entry in logbook.clock_entries)
    assert document.children[0].body == []


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
    assert document.properties is not None
    assert str(document.properties["ID"]) == "two"
    assert str(document.properties["CATEGORY"]) == "work"
    assert isinstance(document.logbook, Logbook)
    assert document.logbook is not None
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
    assert heading.properties is not None
    assert str(heading.properties["ID"]) == "two"
    assert isinstance(heading.logbook, Logbook)
    assert heading.logbook is not None
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


def test_dirty_document_drawer_order_is_properties_then_logbook() -> None:
    """Dirty document rendering prints properties before logbook drawers."""
    document = loads("Text\n")
    document.properties = Properties(properties={"ID": RichText("abc")})
    document.logbook = Logbook(
        clock_entries=[Clock(duration="0:30")],
    )

    rendered = str(document)
    assert rendered.index(":PROPERTIES:") < rendered.index(":LOGBOOK:")


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
