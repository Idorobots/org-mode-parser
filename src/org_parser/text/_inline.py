"""Inline rich-text object abstractions for Org Mode content.

These classes model the object-level nodes that can appear inside heading
titles and paragraph text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from org_parser.time import Timestamp

__all__ = [
    "AngleLink",
    "Bold",
    "Citation",
    "Code",
    "CompletionCounter",
    "ExportSnippet",
    "FootnoteReference",
    "InlineObject",
    "InlineSourceBlock",
    "Italic",
    "LineBreak",
    "PlainLink",
    "PlainText",
    "RadioTarget",
    "RegularLink",
    "StrikeThrough",
    "Target",
    "Timestamp",
    "Underline",
    "Verbatim",
]


class InlineObject(Protocol):
    """Protocol for objects that can render themselves to Org syntax."""

    def __str__(self) -> str:
        """Render this inline object to Org text."""
        ...


def _render_parts(parts: list[InlineObject]) -> str:
    """Render a sequence of inline objects to text."""
    return "".join(str(part) for part in parts)


@dataclass(frozen=True, slots=True)
class PlainText:
    """Plain text object."""

    text: str

    def __str__(self) -> str:
        """Render plain text as-is."""
        return self.text


@dataclass(frozen=True, slots=True)
class LineBreak:
    """Hard line break object."""

    trailing: str = ""

    def __str__(self) -> str:
        """Render a hard line break token."""
        return f"\\\\{self.trailing}"


@dataclass(frozen=True, slots=True)
class CompletionCounter:
    """Completion counter object, e.g. ``[1/3]`` or ``[50%]``."""

    value: str

    def __str__(self) -> str:
        """Render completion counter."""
        return f"[{self.value}]"


@dataclass(frozen=True, slots=True)
class Bold:
    """Bold inline markup object."""

    body: list[InlineObject]

    def __str__(self) -> str:
        """Render bold markup."""
        return f"*{_render_parts(self.body)}*"


@dataclass(frozen=True, slots=True)
class Italic:
    """Italic inline markup object."""

    body: list[InlineObject]

    def __str__(self) -> str:
        """Render italic markup."""
        return f"/{_render_parts(self.body)}/"


@dataclass(frozen=True, slots=True)
class Underline:
    """Underline inline markup object."""

    body: list[InlineObject]

    def __str__(self) -> str:
        """Render underline markup."""
        return f"_{_render_parts(self.body)}_"


@dataclass(frozen=True, slots=True)
class StrikeThrough:
    """Strike-through inline markup object."""

    body: list[InlineObject]

    def __str__(self) -> str:
        """Render strike-through markup."""
        return f"+{_render_parts(self.body)}+"


@dataclass(frozen=True, slots=True)
class Verbatim:
    """Verbatim inline markup object."""

    body: str

    def __str__(self) -> str:
        """Render verbatim markup."""
        return f"={self.body}="


@dataclass(frozen=True, slots=True)
class Code:
    """Inline code markup object."""

    body: str

    def __str__(self) -> str:
        """Render code markup."""
        return f"~{self.body}~"


@dataclass(frozen=True, slots=True)
class ExportSnippet:
    """Export snippet object, e.g. ``@@html:<em>@@``."""

    backend: str
    value: str | None = None

    def __str__(self) -> str:
        """Render export snippet."""
        value = self.value if self.value is not None else ""
        return f"@@{self.backend}:{value}@@"


@dataclass(frozen=True, slots=True)
class FootnoteReference:
    """Footnote reference object."""

    label: str | None = None
    definition: list[InlineObject] | None = None

    def __str__(self) -> str:
        """Render footnote reference."""
        if self.definition is None:
            if self.label is None:
                return "[fn:]"
            return f"[fn:{self.label}]"
        definition = _render_parts(self.definition)
        if self.label is None:
            return f"[fn::{definition}]"
        return f"[fn:{self.label}:{definition}]"


@dataclass(frozen=True, slots=True)
class Citation:
    """Citation object."""

    body: str | None = None
    style: str | None = None

    def __str__(self) -> str:
        """Render citation object."""
        style = f"/{self.style}" if self.style is not None else ""
        body = self.body if self.body is not None else ""
        return f"[cite{style}:{body}]"


@dataclass(frozen=True, slots=True)
class InlineSourceBlock:
    """Inline source block object."""

    language: str
    headers: str | None = None
    body: str | None = None

    def __str__(self) -> str:
        """Render inline source block."""
        headers = f"[{self.headers}]" if self.headers is not None else ""
        body = self.body if self.body is not None else ""
        return f"src_{self.language}{headers}{{{body}}}"


@dataclass(frozen=True, slots=True)
class PlainLink:
    """Plain link object."""

    link_type: str
    path: str

    def __str__(self) -> str:
        """Render plain link."""
        return f"{self.link_type}:{self.path}"


@dataclass(frozen=True, slots=True)
class AngleLink:
    """Angle link object."""

    path: str
    link_type: str | None = None

    def __str__(self) -> str:
        """Render angle link."""
        if self.link_type is None:
            return f"<{self.path}>"
        return f"<{self.link_type}:{self.path}>"


@dataclass(frozen=True, slots=True)
class RegularLink:
    """Regular bracket link object."""

    path: str
    description: list[InlineObject] | None = None

    def __str__(self) -> str:
        """Render regular link."""
        if self.description is None:
            return f"[[{self.path}]]"
        return f"[[{self.path}][{_render_parts(self.description)}]]"


@dataclass(frozen=True, slots=True)
class Target:
    """Target object, e.g. ``<<name>>``."""

    value: str

    def __str__(self) -> str:
        """Render target."""
        return f"<<{self.value}>>"


@dataclass(frozen=True, slots=True)
class RadioTarget:
    """Radio target object, e.g. ``<<<phrase>>>``."""

    body: list[InlineObject]

    def __str__(self) -> str:
        """Render radio target."""
        return f"<<<{_render_parts(self.body)}>>>"
