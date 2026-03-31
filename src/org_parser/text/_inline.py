"""Inline rich-text object abstractions for Org Mode content.

These classes model the object-level nodes that can appear inside heading
titles and paragraph text.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "AngleLink",
    "Bold",
    "Citation",
    "Code",
    "CompletionCounter",
    "ExportSnippet",
    "FootnoteReference",
    "InlineBabelCall",
    "InlineEntity",
    "InlineObject",
    "InlineSourceBlock",
    "Italic",
    "LineBreak",
    "Macro",
    "PlainLink",
    "PlainText",
    "RadioTarget",
    "RegularLink",
    "StrikeThrough",
    "Subscript",
    "Superscript",
    "Target",
    "Underline",
    "Verbatim",
]


class InlineObject:
    """Base class for inline markup objects."""

    __slots__ = ()

    def __str__(self) -> str:
        """Render this inline object to Org text."""
        return ""

    def reformat(self) -> None:
        """No-op reformat for immutable inline objects."""


def _render_parts(parts: list[InlineObject]) -> str:
    """Render a sequence of inline objects to text."""
    return "".join(str(part) for part in parts)


@dataclass(frozen=True, slots=True)
class PlainText(InlineObject):
    """Plain text object."""

    text: str

    def __str__(self) -> str:
        """Render plain text as-is."""
        return self.text


@dataclass(frozen=True, slots=True)
class LineBreak(InlineObject):
    """Hard line break object."""

    trailing: str = ""

    def __str__(self) -> str:
        """Render a hard line break token."""
        return f"\\\\{self.trailing}"


@dataclass(frozen=True, slots=True)
class InlineEntity(InlineObject):
    r"""Org entity inline object.

    Represents named entities (e.g. ``\alpha``, ``\\Rightarrow``) and the
    non-breaking-space form ``\\_ `` (backslash-underscore followed by one or
    more spaces).

    For named entities ``has_braces`` indicates whether the ``{}`` suffix was
    written (``\alpha{}``), which prevents the entity name from merging with
    adjacent text in some export backends.

    The ``\\_ `` form is represented with ``name="_"``.  Its ``__str__``
    always emits a single trailing space; round-trip fidelity for multiple
    trailing spaces relies on the parse-tree-backed source slice in
    [org_parser.text.RichText][].

    Args:
        name: Entity name (e.g. ``"alpha"``) or ``"_"`` for the ``\\_ `` form.
        has_braces: Whether the ``{}`` suffix was written (named entities only).
    """

    name: str
    has_braces: bool = False

    def __str__(self) -> str:
        """Render entity to Org syntax."""
        if self.name == "_":
            return "\\_ "
        suffix = "{}" if self.has_braces else ""
        return f"\\{self.name}{suffix}"


@dataclass(frozen=True, slots=True)
class CompletionCounter(InlineObject):
    """Completion counter object, e.g. ``[1/3]`` or ``[50%]``.

    Example:
    ```python
    >>> from org_parser.text import CompletionCounter
    >>> document = loads("* Heading")
    >>> document[0].counter = CompletionCounter("1/3")
    >>> print(str(document))
    * [1/3] Heading
    ```
    """

    value: str

    def __str__(self) -> str:
        """Render completion counter."""
        return f"[{self.value}]"


@dataclass(frozen=True, slots=True)
class Bold(InlineObject):
    """Bold inline markup object."""

    body: list[InlineObject]

    def __str__(self) -> str:
        """Render bold markup."""
        return f"*{_render_parts(self.body)}*"


@dataclass(frozen=True, slots=True)
class Italic(InlineObject):
    """Italic inline markup object."""

    body: list[InlineObject]

    def __str__(self) -> str:
        """Render italic markup."""
        return f"/{_render_parts(self.body)}/"


@dataclass(frozen=True, slots=True)
class Underline(InlineObject):
    """Underline inline markup object."""

    body: list[InlineObject]

    def __str__(self) -> str:
        """Render underline markup."""
        return f"_{_render_parts(self.body)}_"


@dataclass(frozen=True, slots=True)
class StrikeThrough(InlineObject):
    """Strike-through inline markup object."""

    body: list[InlineObject]

    def __str__(self) -> str:
        """Render strike-through markup."""
        return f"+{_render_parts(self.body)}+"


@dataclass(frozen=True, slots=True)
class Subscript(InlineObject):
    """Subscript inline object."""

    body: list[InlineObject]
    form: str = "{}"

    def __str__(self) -> str:
        """Render subscript markup."""
        if self.form == "*":
            return "_*"
        if self.form == "()":
            return f"_({_render_parts(self.body)})"
        return f"_{{{_render_parts(self.body)}}}"


@dataclass(frozen=True, slots=True)
class Superscript(InlineObject):
    """Superscript inline object."""

    body: list[InlineObject]
    form: str = "{}"

    def __str__(self) -> str:
        """Render superscript markup."""
        if self.form == "*":
            return "^*"
        if self.form == "()":
            return f"^({_render_parts(self.body)})"
        return f"^{{{_render_parts(self.body)}}}"


@dataclass(frozen=True, slots=True)
class Verbatim(InlineObject):
    """Verbatim inline markup object."""

    body: str

    def __str__(self) -> str:
        """Render verbatim markup."""
        return f"={self.body}="


@dataclass(frozen=True, slots=True)
class Code(InlineObject):
    """Inline code markup object."""

    body: str

    def __str__(self) -> str:
        """Render code markup."""
        return f"~{self.body}~"


@dataclass(frozen=True, slots=True)
class ExportSnippet(InlineObject):
    """Export snippet object, e.g. ``@@html:<em>@@``."""

    backend: str
    value: str | None = None

    def __str__(self) -> str:
        """Render export snippet."""
        value = self.value if self.value is not None else ""
        return f"@@{self.backend}:{value}@@"


@dataclass(frozen=True, slots=True)
class FootnoteReference(InlineObject):
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
class Citation(InlineObject):
    """Citation object."""

    body: str | None = None
    style: str | None = None

    def __str__(self) -> str:
        """Render citation object."""
        style = f"/{self.style}" if self.style is not None else ""
        body = self.body if self.body is not None else ""
        return f"[cite{style}:{body}]"


@dataclass(frozen=True, slots=True)
class InlineSourceBlock(InlineObject):
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
class Macro(InlineObject):
    """Macro call object, e.g. ``{{{name}}}`` or ``{{{name(args)}}}``."""

    name: str
    arguments: str | None = None

    def __str__(self) -> str:
        """Render macro call."""
        if self.arguments is not None:
            return "{{{" + self.name + "(" + self.arguments + ")}}}"
        return "{{{" + self.name + "}}}"


@dataclass(frozen=True, slots=True)
class InlineBabelCall(InlineObject):
    """Inline babel call object, e.g. ``call_double[:exports none](n=4)``.

    Represents the inline form of an Org babel call that can appear inside
    paragraph text and heading titles.

    Args:
        name: The called function name.
        arguments: Optional argument string inside ``(…)``.
        inside_header: Optional header string inside the first ``[…]``.
        outside_header: Optional header string inside the second ``[…]``.
    """

    name: str
    arguments: str | None = None
    inside_header: str | None = None
    outside_header: str | None = None

    def __str__(self) -> str:
        """Render inline babel call."""
        inside = f"[{self.inside_header}]" if self.inside_header is not None else ""
        args = self.arguments if self.arguments is not None else ""
        outside = f"[{self.outside_header}]" if self.outside_header is not None else ""
        return f"call_{self.name}{inside}({args}){outside}"


@dataclass(frozen=True, slots=True)
class PlainLink(InlineObject):
    """Plain link object."""

    link_type: str
    path: str

    def __str__(self) -> str:
        """Render plain link."""
        return f"{self.link_type}:{self.path}"


@dataclass(frozen=True, slots=True)
class AngleLink(InlineObject):
    """Angle link object."""

    path: str
    link_type: str | None = None

    def __str__(self) -> str:
        """Render angle link."""
        if self.link_type is None:
            return f"<{self.path}>"
        return f"<{self.link_type}:{self.path}>"


@dataclass(frozen=True, slots=True)
class RegularLink(InlineObject):
    """Regular bracket link object."""

    path: str
    description: list[InlineObject] | None = None

    def __str__(self) -> str:
        """Render regular link."""
        if self.description is None:
            return f"[[{self.path}]]"
        return f"[[{self.path}][{_render_parts(self.description)}]]"


@dataclass(frozen=True, slots=True)
class Target(InlineObject):
    """Target object, e.g. ``<<name>>``."""

    value: str

    def __str__(self) -> str:
        """Render target."""
        return f"<<{self.value}>>"


@dataclass(frozen=True, slots=True)
class RadioTarget(InlineObject):
    """Radio target object, e.g. ``<<<phrase>>>``."""

    body: list[InlineObject]

    def __str__(self) -> str:
        """Render radio target."""
        return f"<<<{_render_parts(self.body)}>>>"
