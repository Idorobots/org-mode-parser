"""Tests for drawer semantic element abstractions."""

from __future__ import annotations

from org_parser import loads
from org_parser.element import Drawer, Logbook, Properties
from org_parser.text import RichText
from org_parser.time import Clock


def test_property_drawer_parses_to_properties_mapping() -> None:
    """Property drawers are parsed to dictionary-like ``Properties`` objects."""
    document = loads(":PROPERTIES:\n:ID: alpha\n:CATEGORY: work\n:END:\n")

    assert isinstance(document.body[0], Properties)
    properties = document.body[0]
    assert properties.node_type == "property_drawer"
    assert str(properties["ID"]) == "alpha"
    assert str(properties["CATEGORY"]) == "work"


def test_properties_support_last_one_wins() -> None:
    """Duplicate property keys keep the value from the last entry."""
    document = loads(":PROPERTIES:\n:ID: old\n:ID: new\n:END:\n")

    assert isinstance(document.body[0], Properties)
    properties = document.body[0]
    assert str(properties["ID"]) == "new"


def test_properties_are_mutable_and_dirty_on_set() -> None:
    """Setting one property value marks owning structures as dirty."""
    document = loads(":PROPERTIES:\n:ID: alpha\n:END:\n")

    assert isinstance(document.body[0], Properties)
    properties = document.body[0]
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

    assert isinstance(document.body[0], Properties)
    properties = document.body[0]

    properties["NAME"].text = "new"

    assert properties.dirty is True
    assert document.dirty is True
    assert str(properties) == ":PROPERTIES:\n:NAME: new\n:END:\n"


def test_heading_properties_drawer_is_exposed_in_heading_body() -> None:
    """Heading-level property drawers are included in heading body elements."""
    document = loads("* H\n:PROPERTIES:\n:ID: abc\n:END:\n")

    assert isinstance(document.children[0].body[0], Properties)


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

    assert isinstance(document.children[0].body[0], Logbook)
    logbook = document.children[0].body[0]
    assert len(logbook.clock_entries) == 2
    assert all(isinstance(entry, Clock) for entry in logbook.clock_entries)
    assert len(logbook.repeats) == 1
    assert logbook.repeats[0].parent is logbook
    assert all(entry.parent is logbook for entry in logbook.clock_entries)


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
