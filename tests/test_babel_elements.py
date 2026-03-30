"""Tests for BabelCall element and InlineBabelCall inline object wrappers."""

from __future__ import annotations

import pytest

from org_parser import loads
from org_parser.element import BabelCall
from org_parser.text import InlineBabelCall, PlainText

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _first_babel_call(org_text: str) -> BabelCall:
    """Parse *org_text* and return the first BabelCall body element."""
    doc = loads(org_text)
    for element in doc.body:
        if isinstance(element, BabelCall):
            return element
    raise AssertionError("No BabelCall found in document body")


def _first_inline_babel_call(org_text: str) -> InlineBabelCall:
    """Parse *org_text* and return the first InlineBabelCall inline object."""
    doc = loads(org_text)
    for element in doc.body:
        from org_parser.element import Paragraph

        if isinstance(element, Paragraph):
            for part in element.body.parts:
                if isinstance(part, InlineBabelCall):
                    return part
    raise AssertionError("No InlineBabelCall found in document body")


# ===========================================================================
# BabelCall — construction
# ===========================================================================


class TestBabelCallConstruction:
    """Tests for manually constructed :class:`BabelCall` instances."""

    def test_minimum_construction(self) -> None:
        """BabelCall with name only sets optional fields to None."""
        bc = BabelCall(name="myfunc")
        assert bc.name == "myfunc"
        assert bc.arguments is None
        assert bc.inside_header is None
        assert bc.outside_header is None
        assert bc.dirty is False
        assert bc.parent is None

    def test_full_construction(self) -> None:
        """BabelCall accepts all optional fields."""
        bc = BabelCall(
            name="double",
            arguments="n=4",
            inside_header=":exports none",
            outside_header=":results value",
        )
        assert bc.name == "double"
        assert bc.arguments == "n=4"
        assert bc.inside_header == ":exports none"
        assert bc.outside_header == ":results value"


# ===========================================================================
# BabelCall — parsing
# ===========================================================================


class TestBabelCallParsing:
    """Tests for :meth:`BabelCall.from_node` via :func:`loads`."""

    def test_bare(self) -> None:
        """#+call: myfunc() parses to BabelCall with name only."""
        bc = _first_babel_call("#+call: myfunc()\n")
        assert bc.name == "myfunc"
        assert bc.arguments is None
        assert bc.inside_header is None
        assert bc.outside_header is None

    def test_with_arguments(self) -> None:
        """#+call: double(n=4) captures the argument string."""
        bc = _first_babel_call("#+call: double(n=4)\n")
        assert bc.name == "double"
        assert bc.arguments == "n=4"
        assert bc.inside_header is None
        assert bc.outside_header is None

    def test_with_inside_header(self) -> None:
        """#+call: myfunc[:exports none]() captures inside_header."""
        bc = _first_babel_call("#+call: myfunc[:exports none]()\n")
        assert bc.name == "myfunc"
        assert bc.inside_header == ":exports none"
        assert bc.arguments is None
        assert bc.outside_header is None

    def test_with_outside_header(self) -> None:
        """#+call: myfunc()[:results output] captures outside_header."""
        bc = _first_babel_call("#+call: myfunc()[:results output]\n")
        assert bc.name == "myfunc"
        assert bc.outside_header == ":results output"
        assert bc.arguments is None
        assert bc.inside_header is None

    def test_full_form(self) -> None:
        """#+call: double[:exports none](n=4)[:results value] captures all fields."""
        bc = _first_babel_call("#+call: double[:exports none](n=4)[:results value]\n")
        assert bc.name == "double"
        assert bc.inside_header == ":exports none"
        assert bc.arguments == "n=4"
        assert bc.outside_header == ":results value"

    def test_case_insensitive_keyword(self) -> None:
        """#+CALL: is accepted regardless of case."""
        bc = _first_babel_call("#+CALL: myfunc()\n")
        assert bc.name == "myfunc"

    def test_parsed_instance_is_not_dirty(self) -> None:
        """Freshly parsed BabelCall is clean (not dirty)."""
        bc = _first_babel_call("#+call: myfunc()\n")
        assert bc.dirty is False


# ===========================================================================
# BabelCall — __str__ rendering
# ===========================================================================


class TestBabelCallStr:
    """Tests for :meth:`BabelCall.__str__`."""

    def test_clean_str_is_verbatim_source(self) -> None:
        """Clean parse-backed BabelCall returns verbatim source."""
        src = "#+call: myfunc()\n"
        bc = _first_babel_call(src)
        assert str(bc) == src

    def test_clean_full_form_str_is_verbatim_source(self) -> None:
        """Clean full-form parse-backed BabelCall returns verbatim source."""
        src = "#+call: double[:exports none](n=4)[:results value]\n"
        bc = _first_babel_call(src)
        assert str(bc) == src

    def test_dirty_bare_str(self) -> None:
        """Dirty BabelCall with name only renders without optional components."""
        bc = BabelCall(name="myfunc")
        assert str(bc) == "#+call: myfunc()\n"

    def test_dirty_with_arguments_str(self) -> None:
        """Dirty BabelCall with arguments renders correctly."""
        bc = BabelCall(name="double", arguments="n=4")
        assert str(bc) == "#+call: double(n=4)\n"

    def test_dirty_with_inside_header_str(self) -> None:
        """Dirty BabelCall with inside_header renders correctly."""
        bc = BabelCall(name="myfunc", inside_header=":exports none")
        assert str(bc) == "#+call: myfunc[:exports none]()\n"

    def test_dirty_with_outside_header_str(self) -> None:
        """Dirty BabelCall with outside_header renders correctly."""
        bc = BabelCall(name="myfunc", outside_header=":results output")
        assert str(bc) == "#+call: myfunc()[:results output]\n"

    def test_dirty_full_form_str(self) -> None:
        """Dirty BabelCall with all fields renders correctly."""
        bc = BabelCall(
            name="double",
            arguments="n=4",
            inside_header=":exports none",
            outside_header=":results value",
        )
        assert str(bc) == "#+call: double[:exports none](n=4)[:results value]\n"

    def test_setter_marks_dirty_and_str_reconstructs(self) -> None:
        """Setting a field on a parse-backed instance switches to reconstructed mode."""
        bc = _first_babel_call("#+call: myfunc()\n")
        assert bc.dirty is False
        bc.name = "renamed"
        assert bc.dirty is True
        assert str(bc) == "#+call: renamed()\n"


# ===========================================================================
# BabelCall — setters
# ===========================================================================


class TestBabelCallSetters:
    """Tests for :class:`BabelCall` property setters."""

    def test_name_setter_marks_dirty(self) -> None:
        """name setter marks BabelCall dirty."""
        bc = BabelCall(name="original")
        bc.name = "changed"
        assert bc.dirty is True
        assert bc.name == "changed"

    def test_arguments_setter_marks_dirty(self) -> None:
        """arguments setter marks BabelCall dirty."""
        bc = BabelCall(name="f")
        bc.arguments = "x=1"
        assert bc.dirty is True
        assert bc.arguments == "x=1"

    def test_arguments_setter_clears_to_none(self) -> None:
        """arguments setter accepts None."""
        bc = BabelCall(name="f", arguments="x=1")
        bc.arguments = None
        assert bc.arguments is None

    def test_inside_header_setter_marks_dirty(self) -> None:
        """inside_header setter marks BabelCall dirty."""
        bc = BabelCall(name="f")
        bc.inside_header = ":exports none"
        assert bc.dirty is True
        assert bc.inside_header == ":exports none"

    def test_outside_header_setter_marks_dirty(self) -> None:
        """outside_header setter marks BabelCall dirty."""
        bc = BabelCall(name="f")
        bc.outside_header = ":results value"
        assert bc.dirty is True
        assert bc.outside_header == ":results value"


# ===========================================================================
# BabelCall — __repr__
# ===========================================================================


class TestBabelCallRepr:
    """Tests for :meth:`BabelCall.__repr__`."""

    def test_repr_name_only(self) -> None:
        """__repr__ includes only name when optionals are None."""
        bc = BabelCall(name="myfunc")
        assert repr(bc) == "BabelCall(name='myfunc')"

    def test_repr_full(self) -> None:
        """__repr__ includes all provided fields."""
        bc = BabelCall(
            name="double",
            arguments="n=4",
            inside_header=":exports none",
            outside_header=":results value",
        )
        assert repr(bc) == (
            "BabelCall("
            "name='double', "
            "arguments='n=4', "
            "inside_header=':exports none', "
            "outside_header=':results value')"
        )


# ===========================================================================
# InlineBabelCall — construction
# ===========================================================================


class TestInlineBabelCallConstruction:
    """Tests for manually constructed :class:`InlineBabelCall` instances."""

    def test_minimum_construction(self) -> None:
        """InlineBabelCall with name only sets optional fields to None."""
        ibc = InlineBabelCall(name="myfunc")
        assert ibc.name == "myfunc"
        assert ibc.arguments is None
        assert ibc.inside_header is None
        assert ibc.outside_header is None

    def test_full_construction(self) -> None:
        """InlineBabelCall accepts all optional fields."""
        ibc = InlineBabelCall(
            name="double",
            arguments="n=4",
            inside_header=":exports none",
            outside_header=":results value",
        )
        assert ibc.name == "double"
        assert ibc.arguments == "n=4"
        assert ibc.inside_header == ":exports none"
        assert ibc.outside_header == ":results value"

    def test_is_frozen(self) -> None:
        """InlineBabelCall is immutable (frozen dataclass)."""
        ibc = InlineBabelCall(name="myfunc")
        with pytest.raises((AttributeError, TypeError)):
            ibc.name = "other"  # type: ignore[misc]


# ===========================================================================
# InlineBabelCall — parsing
# ===========================================================================


class TestInlineBabelCallParsing:
    """Tests for inline_babel_call parsing via :func:`loads`."""

    def test_bare(self) -> None:
        """call_myfunc() in a paragraph parses to InlineBabelCall with name only."""
        ibc = _first_inline_babel_call("call_myfunc()\n")
        assert ibc.name == "myfunc"
        assert ibc.arguments is None
        assert ibc.inside_header is None
        assert ibc.outside_header is None

    def test_with_arguments(self) -> None:
        """call_double(n=4) captures the argument string."""
        ibc = _first_inline_babel_call("call_double(n=4)\n")
        assert ibc.name == "double"
        assert ibc.arguments == "n=4"

    def test_with_inside_header(self) -> None:
        """call_myfunc[:exports none]() captures inside_header."""
        ibc = _first_inline_babel_call("call_myfunc[:exports none]()\n")
        assert ibc.name == "myfunc"
        assert ibc.inside_header == ":exports none"
        assert ibc.arguments is None

    def test_with_outside_header(self) -> None:
        """call_myfunc()[:results value] captures outside_header."""
        ibc = _first_inline_babel_call("call_myfunc()[:results value]\n")
        assert ibc.name == "myfunc"
        assert ibc.arguments is None
        assert ibc.inside_header is None
        assert ibc.outside_header == ":results value"

    def test_full_form(self) -> None:
        """call_double[:exports none](n=4)[:results value] captures all fields."""
        ibc = _first_inline_babel_call("call_double[:exports none](n=4)[:results value]\n")
        assert ibc.name == "double"
        assert ibc.inside_header == ":exports none"
        assert ibc.arguments == "n=4"
        assert ibc.outside_header == ":results value"

    def test_embedded_in_paragraph(self) -> None:
        """InlineBabelCall is recognized mid-paragraph alongside plain text."""
        doc = loads("Result: call_double(n=2) is the answer.\n")
        from org_parser.element import Paragraph

        para = next(e for e in doc.body if isinstance(e, Paragraph))
        types = [type(p) for p in para.body.parts]
        assert InlineBabelCall in types
        assert PlainText in types


# ===========================================================================
# InlineBabelCall — __str__ rendering
# ===========================================================================


class TestInlineBabelCallStr:
    """Tests for :meth:`InlineBabelCall.__str__`."""

    def test_bare_str(self) -> None:
        """Bare InlineBabelCall renders as call_name()."""
        ibc = InlineBabelCall(name="myfunc")
        assert str(ibc) == "call_myfunc()"

    def test_with_arguments_str(self) -> None:
        """InlineBabelCall with arguments renders correctly."""
        ibc = InlineBabelCall(name="double", arguments="n=4")
        assert str(ibc) == "call_double(n=4)"

    def test_with_inside_header_str(self) -> None:
        """InlineBabelCall with inside_header renders correctly."""
        ibc = InlineBabelCall(name="myfunc", inside_header=":exports none")
        assert str(ibc) == "call_myfunc[:exports none]()"

    def test_with_outside_header_str(self) -> None:
        """InlineBabelCall with outside_header renders correctly."""
        ibc = InlineBabelCall(name="myfunc", outside_header=":results value")
        assert str(ibc) == "call_myfunc()[:results value]"

    def test_full_form_str(self) -> None:
        """InlineBabelCall with all fields renders correctly."""
        ibc = InlineBabelCall(
            name="double",
            arguments="n=4",
            inside_header=":exports none",
            outside_header=":results value",
        )
        assert str(ibc) == "call_double[:exports none](n=4)[:results value]"
