"""Semantic element classes for Org block nodes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import node_source
from org_parser._nodes import INDENT, SPECIAL_KEYWORD
from org_parser.element._dispatch import body_element_factories
from org_parser.element._element import (
    Element,
    build_semantic_repr,
    element_from_error_or_unknown,
    ensure_trailing_newline,
)
from org_parser.element._structure import Indent

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    import tree_sitter

    from org_parser.document._document import Document
    from org_parser.document._heading import Heading

__all__ = [
    "CenterBlock",
    "CommentBlock",
    "DynamicBlock",
    "ExampleBlock",
    "ExportBlock",
    "FixedWidthBlock",
    "QuoteBlock",
    "SourceBlock",
    "SpecialBlock",
    "VerseBlock",
]


class _ContainerBlock(Element):
    """Base class for blocks whose contents are nested elements."""

    def __init__(
        self,
        *,
        begin_line: str,
        end_line: str,
        body: list[Element] | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._begin_line = begin_line
        self._end_line = end_line
        self._body = body if body is not None else []
        self._adopt_body(self._body)

    @property
    def body(self) -> list[Element]:
        """Mutable block contents as semantic elements."""
        return self._body

    @body.setter
    def body(self, value: list[Element]) -> None:
        """Set block contents and mark this block as dirty."""
        self._body = value
        self._adopt_body(self._body)
        self.mark_dirty()

    @property
    def body_text(self) -> str:
        """Stringified text of all nested block body elements."""
        return "".join(str(element) for element in self._body)

    def reformat(self) -> None:
        """Mark contents and this block dirty for scratch-built rendering."""
        for element in self._body:
            element.reformat()
        self.mark_dirty()

    def _adopt_body(self, body: Sequence[Element]) -> None:
        """Assign this block as parent for each nested element."""
        for element in body:
            element.parent = self

    def _render_body(self) -> str:
        """Render nested contents ensuring one trailing newline per child."""
        return "".join(ensure_trailing_newline(str(element)) for element in self._body)

    def __str__(self) -> str:
        """Render block text preserving source while parse-backed and clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        return f"{self._begin_line}\n{self._render_body()}{self._end_line}\n"

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr(
            self.__class__.__name__,
            begin_line=self._begin_line,
            body=self._body,
        )

    def __iter__(self) -> Iterator[Element]:
        """Iterate over body elements."""
        return iter(self._body)

    def __len__(self) -> int:
        """Return number of body elements."""
        return len(self._body)

    def __getitem__(self, index: int | slice) -> Element | list[Element]:
        """Return one body element (or body slice)."""
        return self._body[index]


class _TextBlock(Element):
    """Base class for blocks whose contents are plain mutable text."""

    def __init__(
        self,
        *,
        begin_line: str,
        end_line: str,
        body: str,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._begin_line = begin_line
        self._end_line = end_line
        self._body = body

    @property
    def body(self) -> str:
        """Mutable block contents text without delimiters."""
        return self._body

    @body.setter
    def body(self, value: str) -> None:
        """Set block contents text and mark this block as dirty."""
        self._body = value
        self.mark_dirty()

    def __str__(self) -> str:
        """Render block text preserving source while parse-backed and clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)
        content = _ensure_single_trailing_newline(self._body)
        return f"{self._begin_line}\n{content}{self._end_line}\n"

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr(
            self.__class__.__name__,
            begin_line=self._begin_line,
            body=self._body,
        )


class CenterBlock(_ContainerBlock):
    """``#+begin_center`` block with mutable nested element contents."""

    def __init__(
        self,
        *,
        parameters: str | None = None,
        body: list[Element] | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        self._parameters = _normalize_optional_text(parameters)
        super().__init__(
            begin_line=_render_begin_line("center", self._parameters),
            end_line="#+end_center",
            body=body,
            parent=parent,
        )

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> CenterBlock:
        """Create a :class:`CenterBlock` from a ``center_block`` node."""
        source_text = node_source(node, document)
        block = cls(
            parameters=_extract_optional_field_text(node, document, "parameters")
            or _extract_begin_parameters(source_text, "#+begin_center"),
            body=_extract_container_contents(node, document),
            parent=parent,
        )
        block._node = node
        block._document = document
        return block

    @property
    def parameters(self) -> str | None:
        """Optional trailing parameters from the begin line."""
        return self._parameters

    @parameters.setter
    def parameters(self, value: str | None) -> None:
        """Set begin-line parameters and mark this block as dirty."""
        self._parameters = _normalize_optional_text(value)
        self._begin_line = _render_begin_line("center", self._parameters)
        self.mark_dirty()


class QuoteBlock(_ContainerBlock):
    """``#+begin_quote`` block with mutable nested element contents."""

    def __init__(
        self,
        *,
        parameters: str | None = None,
        body: list[Element] | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        self._parameters = _normalize_optional_text(parameters)
        super().__init__(
            begin_line=_render_begin_line("quote", self._parameters),
            end_line="#+end_quote",
            body=body,
            parent=parent,
        )

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> QuoteBlock:
        """Create a :class:`QuoteBlock` from a ``quote_block`` node."""
        source_text = node_source(node, document)
        block = cls(
            parameters=_extract_optional_field_text(node, document, "parameters")
            or _extract_begin_parameters(source_text, "#+begin_quote"),
            body=_extract_container_contents(node, document),
            parent=parent,
        )
        block._node = node
        block._document = document
        return block

    @property
    def parameters(self) -> str | None:
        """Optional trailing parameters from the begin line."""
        return self._parameters

    @parameters.setter
    def parameters(self, value: str | None) -> None:
        """Set begin-line parameters and mark this block as dirty."""
        self._parameters = _normalize_optional_text(value)
        self._begin_line = _render_begin_line("quote", self._parameters)
        self.mark_dirty()


class SpecialBlock(_ContainerBlock):
    """``#+begin_<name>`` block with mutable nested element contents."""

    def __init__(
        self,
        *,
        name: str,
        parameters: str | None = None,
        body: list[Element] | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        self._name = name
        self._parameters = _normalize_optional_text(parameters)
        super().__init__(
            begin_line=_render_begin_line(name, self._parameters),
            end_line=f"#+end_{name}",
            body=body,
            parent=parent,
        )

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> SpecialBlock:
        """Create a :class:`SpecialBlock` from a ``special_block`` node."""
        source_text = node_source(node, document)
        name = _extract_optional_field_text(node, document, "name")
        parsed_name, parsed_parameters = _extract_special_begin_data(source_text)
        block = cls(
            name=parsed_name if name is None else name,
            parameters=_extract_optional_field_text(node, document, "parameters")
            or parsed_parameters,
            body=_extract_container_contents(node, document),
            parent=parent,
        )
        block._node = node
        block._document = document
        return block

    @property
    def name(self) -> str:
        """Special block name (the ``<name>`` in ``#+begin_<name>``)."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set block name and mark this block as dirty."""
        self._name = value
        self._begin_line = _render_begin_line(self._name, self._parameters)
        self._end_line = f"#+end_{self._name}"
        self.mark_dirty()

    @property
    def parameters(self) -> str | None:
        """Optional trailing parameters from the begin line."""
        return self._parameters

    @parameters.setter
    def parameters(self, value: str | None) -> None:
        """Set begin-line parameters and mark this block as dirty."""
        self._parameters = _normalize_optional_text(value)
        self._begin_line = _render_begin_line(self._name, self._parameters)
        self.mark_dirty()


class DynamicBlock(_ContainerBlock):
    """``#+begin:`` dynamic block with mutable nested element contents."""

    def __init__(
        self,
        *,
        name: str,
        parameters: str | None = None,
        body: list[Element] | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        self._name = name
        self._parameters = _normalize_optional_text(parameters)
        super().__init__(
            begin_line=_render_dynamic_begin_line(name, self._parameters),
            end_line="#+end:",
            body=body,
            parent=parent,
        )

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> DynamicBlock:
        """Create a :class:`DynamicBlock` from a ``dynamic_block`` node."""
        source_text = node_source(node, document)
        name = _extract_optional_field_text(node, document, "name")
        parsed_name, parsed_parameters = _extract_dynamic_begin_data(source_text)
        block = cls(
            name=parsed_name if name is None else name,
            parameters=_extract_optional_field_text(node, document, "parameters")
            or parsed_parameters,
            body=_extract_container_contents(node, document),
            parent=parent,
        )
        block._node = node
        block._document = document
        return block

    @property
    def name(self) -> str:
        """Dynamic block name from the begin line."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set dynamic block name and mark this block as dirty."""
        self._name = value
        self._begin_line = _render_dynamic_begin_line(self._name, self._parameters)
        self.mark_dirty()

    @property
    def parameters(self) -> str | None:
        """Optional trailing parameters from the begin line."""
        return self._parameters

    @parameters.setter
    def parameters(self, value: str | None) -> None:
        """Set begin-line parameters and mark this block as dirty."""
        self._parameters = _normalize_optional_text(value)
        self._begin_line = _render_dynamic_begin_line(self._name, self._parameters)
        self.mark_dirty()


class VerseBlock(_ContainerBlock):
    """``#+begin_verse`` block with mutable nested element contents."""

    def __init__(
        self,
        *,
        body: list[Element] | None = None,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(
            begin_line="#+begin_verse",
            end_line="#+end_verse",
            body=body,
            parent=parent,
        )

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> VerseBlock:
        """Create a :class:`VerseBlock` from a ``verse_block`` node."""
        block = cls(
            body=_extract_container_contents(node, document),
            parent=parent,
        )
        block._node = node
        block._document = document
        return block


class CommentBlock(_TextBlock):
    """``#+begin_comment`` block with mutable raw text contents."""

    def __init__(
        self,
        *,
        body: str,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(
            begin_line="#+begin_comment",
            end_line="#+end_comment",
            body=body,
            parent=parent,
        )

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> CommentBlock:
        """Create a :class:`CommentBlock` from a ``comment_block`` node."""
        source_text = node_source(node, document)
        block = cls(
            body=_extract_block_body_text(source_text),
            parent=parent,
        )
        block._node = node
        block._document = document
        return block


class ExampleBlock(_TextBlock):
    """``#+begin_example`` block with mutable raw text contents."""

    def __init__(
        self,
        *,
        parameters: str | None = None,
        body: str,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        self._parameters = _normalize_optional_text(parameters)
        super().__init__(
            begin_line=_render_begin_line("example", self._parameters),
            end_line="#+end_example",
            body=body,
            parent=parent,
        )

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> ExampleBlock:
        """Create a :class:`ExampleBlock` from an ``example_block`` node."""
        source_text = node_source(node, document)
        block = cls(
            parameters=_extract_optional_field_text(node, document, "parameters")
            or _extract_begin_parameters(source_text, "#+begin_example"),
            body=_extract_block_body_text(source_text),
            parent=parent,
        )
        block._node = node
        block._document = document
        return block

    @property
    def parameters(self) -> str | None:
        """Optional trailing parameters from the begin line."""
        return self._parameters

    @parameters.setter
    def parameters(self, value: str | None) -> None:
        """Set begin-line parameters and mark this block as dirty."""
        self._parameters = _normalize_optional_text(value)
        self._begin_line = _render_begin_line("example", self._parameters)
        self.mark_dirty()


class ExportBlock(_TextBlock):
    """``#+begin_export`` block with mutable raw text contents."""

    def __init__(
        self,
        *,
        backend: str,
        parameters: str | None = None,
        body: str,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        self._backend = backend
        self._parameters = _normalize_optional_text(parameters)
        super().__init__(
            begin_line=_render_export_begin_line(self._backend, self._parameters),
            end_line="#+end_export",
            body=body,
            parent=parent,
        )

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> ExportBlock:
        """Create a :class:`ExportBlock` from an ``export_block`` node."""
        source_text = node_source(node, document)
        backend = _extract_optional_field_text(node, document, "backend")
        parsed_backend, parsed_parameters = _extract_export_begin_data(source_text)
        block = cls(
            backend=parsed_backend if backend is None else backend,
            parameters=_extract_optional_field_text(node, document, "parameters")
            or parsed_parameters,
            body=_extract_block_body_text(source_text),
            parent=parent,
        )
        block._node = node
        block._document = document
        return block

    @property
    def backend(self) -> str:
        """Export backend identifier from begin line."""
        return self._backend

    @backend.setter
    def backend(self, value: str) -> None:
        """Set export backend and mark this block as dirty."""
        self._backend = value
        self._begin_line = _render_export_begin_line(self._backend, self._parameters)
        self.mark_dirty()

    @property
    def parameters(self) -> str | None:
        """Optional trailing parameters from the begin line."""
        return self._parameters

    @parameters.setter
    def parameters(self, value: str | None) -> None:
        """Set begin-line parameters and mark this block as dirty."""
        self._parameters = _normalize_optional_text(value)
        self._begin_line = _render_export_begin_line(self._backend, self._parameters)
        self.mark_dirty()


class SourceBlock(_TextBlock):
    """``#+begin_src`` block with mutable source text contents."""

    def __init__(
        self,
        *,
        language: str | None = None,
        switches: str | None = None,
        body: str,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        self._language = _normalize_optional_text(language)
        self._switches = _normalize_optional_text(switches)
        super().__init__(
            begin_line=_render_source_begin_line(self._language, self._switches),
            end_line="#+end_src",
            body=body,
            parent=parent,
        )

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> SourceBlock:
        """Create a :class:`SourceBlock` from a ``src_block`` node."""
        source_text = node_source(node, document)
        parsed_language, parsed_switches = _extract_source_begin_data(source_text)
        block = cls(
            language=_extract_optional_field_text(node, document, "language")
            or parsed_language,
            switches=_extract_optional_field_text(node, document, "switches")
            or parsed_switches,
            body=_extract_block_body_text(source_text),
            parent=parent,
        )
        block._node = node
        block._document = document
        return block

    @property
    def language(self) -> str | None:
        """Optional source language from begin line."""
        return self._language

    @language.setter
    def language(self, value: str | None) -> None:
        """Set source language and mark this block as dirty."""
        self._language = _normalize_optional_text(value)
        self._begin_line = _render_source_begin_line(self._language, self._switches)
        self.mark_dirty()

    @property
    def switches(self) -> str | None:
        """Optional source block switches from begin line."""
        return self._switches

    @switches.setter
    def switches(self, value: str | None) -> None:
        """Set source switches and mark this block as dirty."""
        self._switches = _normalize_optional_text(value)
        self._begin_line = _render_source_begin_line(self._language, self._switches)
        self.mark_dirty()


class FixedWidthBlock(Element):
    """Fixed-width area line with mutable content text."""

    def __init__(
        self,
        *,
        body: str,
        parent: Document | Heading | Element | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self._body = body

    @classmethod
    def from_node(
        cls,
        node: tree_sitter.Node,
        document: Document,
        *,
        parent: Document | Heading | Element | None = None,
    ) -> FixedWidthBlock:
        """Create a :class:`FixedWidthBlock` from a ``fixed_width`` node."""
        source_text = node_source(node, document)
        block = cls(
            body=_extract_fixed_width_contents(source_text),
            parent=parent,
        )
        block._node = node
        block._document = document
        return block

    @property
    def body(self) -> str:
        """Mutable fixed-width content text without ``:`` prefixes."""
        return self._body

    @body.setter
    def body(self, value: str) -> None:
        """Set fixed-width content text and mark this block as dirty."""
        self._body = value
        self.mark_dirty()

    def __str__(self) -> str:
        """Render fixed-width line preserving source while parse-backed and clean."""
        if not self.dirty and self._node is not None and self._document is not None:
            return node_source(self._node, self._document)

        lines = self._body.splitlines()
        if not lines:
            return ":\n"
        rendered = [":\n" if line == "" else f": {line}\n" for line in lines]
        return "".join(rendered)

    def __repr__(self) -> str:
        """Return a tree-oriented representation for debugging."""
        return build_semantic_repr("FixedWidthBlock", body=self._body)


def _extract_container_contents(
    node: tree_sitter.Node,
    document: Document,
) -> list[Element]:
    """Extract nested body elements for container-style blocks.

    Elements are constructed with ``parent=None``; the containing
    :class:`_ContainerBlock` assigns the correct parent via
    :meth:`_adopt_body` after construction.
    """
    elements = [
        _extract_nested_element(child, document, parent=None)
        for child in node.children_by_field_name("body")
        if child.is_named
    ]
    from org_parser.element._structure_recovery import attach_affiliated_keywords

    attach_affiliated_keywords(elements)
    return elements


def _extract_nested_element(
    node: tree_sitter.Node,
    document: Document,
    *,
    parent: Document | Heading | Element | None = None,
) -> Element:
    """Build one semantic element for nested block contents."""
    if node.type == INDENT:
        return _extract_indent(node, document, parent=parent)

    from org_parser.element._keyword import Keyword

    dispatch: dict[str, Callable[..., Element]] = {
        **body_element_factories(),
        SPECIAL_KEYWORD: Keyword.from_node,
    }
    factory = dispatch.get(node.type)
    if factory is None:
        return element_from_error_or_unknown(node, document, parent=parent)
    return factory(node, document, parent=parent)


def _extract_indent(
    node: tree_sitter.Node,
    document: Document,
    *,
    parent: Document | Heading | Element | None = None,
) -> Indent:
    """Build one nested :class:`Indent` from an ``indent`` node."""
    return Indent.from_node(
        node, document, parent=parent, child_factory=_extract_nested_element
    )


def _extract_optional_field_text(
    node: tree_sitter.Node,
    document: Document,
    field_name: str,
) -> str | None:
    """Return text for one optional field node, if present."""
    field_node = node.child_by_field_name(field_name)
    if field_node is None:
        return None
    value = document.source_for(field_node).decode()
    return value if value != "" else None


def _extract_block_body_text(source_text: str) -> str:
    """Return block body text between opening and closing delimiter lines."""
    lines = source_text.splitlines(keepends=True)
    if len(lines) <= 2:
        return ""
    return "".join(lines[1:-1])


def _extract_fixed_width_contents(source_text: str) -> str:
    """Return fixed-width content text without leading prefix markers."""
    line = source_text.rstrip("\n")
    trimmed = line.lstrip(" \t")
    if not trimmed.startswith(":"):
        return ""
    content = trimmed[1:]
    if content.startswith(" "):
        content = content[1:]
    return content


def _extract_begin_parameters(source_text: str, prefix: str) -> str | None:
    """Return trailing begin-line parameters after one exact prefix."""
    line = _first_line(source_text)
    if not line.lower().startswith(prefix.lower()):
        return None
    tail = line[len(prefix) :].strip()
    return tail if tail != "" else None


def _extract_special_begin_data(source_text: str) -> tuple[str, str | None]:
    """Return ``(name, parameters)`` for one ``#+begin_<name>`` line."""
    line = _first_line(source_text).strip()
    lowered = line.lower()
    marker = "#+begin_"
    if not lowered.startswith(marker):
        return "", None
    tail = line[len(marker) :].strip()
    if tail == "":
        return "", None
    name, _, params = tail.partition(" ")
    normalized = params.strip()
    return name, (normalized if normalized != "" else None)


def _extract_dynamic_begin_data(source_text: str) -> tuple[str, str | None]:
    """Return ``(name, parameters)`` for one ``#+begin:`` dynamic line."""
    line = _first_line(source_text).strip()
    marker = "#+begin:"
    if not line.lower().startswith(marker):
        return "", None
    tail = line[len(marker) :].strip()
    if tail == "":
        return "", None
    name, _, params = tail.partition(" ")
    normalized = params.strip()
    return name, (normalized if normalized != "" else None)


def _extract_export_begin_data(source_text: str) -> tuple[str, str | None]:
    """Return ``(backend, parameters)`` for one export block begin line."""
    line = _first_line(source_text).strip()
    marker = "#+begin_export"
    if not line.lower().startswith(marker):
        return "", None
    tail = line[len(marker) :].strip()
    if tail == "":
        return "", None
    backend, _, params = tail.partition(" ")
    normalized = params.strip()
    return backend, (normalized if normalized != "" else None)


def _extract_source_begin_data(source_text: str) -> tuple[str | None, str | None]:
    """Return ``(language, switches)`` for one source block begin line."""
    line = _first_line(source_text).strip()
    marker = "#+begin_src"
    if not line.lower().startswith(marker):
        return None, None
    tail = line[len(marker) :].strip()
    if tail == "":
        return None, None
    language, _, switches = tail.partition(" ")
    normalized_switches = switches.strip()
    return language, (normalized_switches if normalized_switches != "" else None)


def _first_line(value: str) -> str:
    """Return the first line (without newline terminator) from text."""
    first, _, _ = value.partition("\n")
    return first


def _render_begin_line(name: str, parameters: str | None) -> str:
    """Return a canonical ``#+begin_<name>`` line."""
    if parameters is None:
        return f"#+begin_{name}"
    return f"#+begin_{name} {parameters}"


def _render_dynamic_begin_line(name: str, parameters: str | None) -> str:
    """Return a canonical ``#+begin:`` line for dynamic blocks."""
    base = f"#+begin: {name}" if name != "" else "#+begin:"
    if parameters is None:
        return base
    return f"{base} {parameters}".rstrip()


def _render_export_begin_line(backend: str, parameters: str | None) -> str:
    """Return a canonical ``#+begin_export`` line."""
    base = f"#+begin_export {backend}" if backend != "" else "#+begin_export"
    if parameters is None:
        return base
    return f"{base} {parameters}".rstrip()


def _render_source_begin_line(language: str | None, switches: str | None) -> str:
    """Return a canonical ``#+begin_src`` line."""
    if language is None:
        return "#+begin_src"
    if switches is None:
        return f"#+begin_src {language}"
    return f"#+begin_src {language} {switches}"


def _normalize_optional_text(value: str | None) -> str | None:
    """Return stripped text or ``None`` when empty."""
    if value is None:
        return None
    normalized = value.strip()
    if normalized == "":
        return None
    return normalized


def _ensure_single_trailing_newline(value: str) -> str:
    """Return text with exactly one trailing newline when non-empty."""
    if value == "":
        return ""
    return f"{value.rstrip(chr(10))}\n"
