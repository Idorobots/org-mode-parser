"""Semantic recovery helpers for list and block structure."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser._node import node_source
from org_parser.element._list import List, ListItem
from org_parser.element._paragraph import Paragraph
from org_parser.element._structure import BlankLine, IndentBlock
from org_parser.text._rich_text import RichText

if TYPE_CHECKING:
    from org_parser.document._document import Document
    from org_parser.document._heading import Heading
    from org_parser.element._element import Element

__all__ = ["recover_lists"]


def recover_lists(
    elements: list[Element],
    *,
    parent: Document | Heading | Element | None,
) -> list[Element]:
    """Recover semantic lists and paragraph runs from section elements."""
    return _recover_stream(elements, parent=parent, in_block=False, base_indent=0)


def _recover_stream(  # noqa: PLR0915
    elements: list[Element],
    *,
    parent: Document | Heading | Element | None,
    in_block: bool,
    base_indent: int,
) -> list[Element]:
    """Recover one flat element stream, recursively handling indent blocks."""
    recovered: list[Element] = []
    paragraph_run: list[Paragraph] = []
    list_run: list[ListItem] = []

    def flush_paragraph_run() -> None:
        if not paragraph_run:
            return
        if len(paragraph_run) == 1:
            recovered.append(paragraph_run[0])
        else:
            recovered.append(_merge_paragraphs(paragraph_run, parent=parent))
        paragraph_run.clear()

    def flush_list_run() -> None:
        if not list_run:
            return
        recovered.append(List(items=list(list_run), parent=parent))
        list_run.clear()

    def consume(element: Element) -> None:  # noqa: PLR0912
        if isinstance(element, BlankLine):
            flush_paragraph_run()
            if in_block:
                flush_list_run()
                recovered.append(element)
            elif list_run:
                list_run[-1].append_body(element, mark_dirty=False)
            else:
                recovered.append(element)
        elif isinstance(element, ListItem):
            flush_paragraph_run()
            list_run.append(element)
        elif isinstance(element, Paragraph):
            attached = _attach_paragraph_to_pending_item(
                element,
                list_run,
                base_indent=base_indent,
            )
            if not attached:
                flush_list_run()
                paragraph_run.append(element)
        elif isinstance(element, IndentBlock):
            attached = _attach_block_to_pending_item(
                element,
                list_run,
                parent=parent,
                base_indent=base_indent,
            )
            if not attached:
                block_indent = _indent_width(element.indent)
                if element.indent is None:
                    block_indent = base_indent

                nested = _recover_stream(
                    element.body,
                    parent=parent,
                    in_block=True,
                    base_indent=block_indent,
                )

                if block_indent == base_indent:
                    for nested_element in nested:
                        consume(nested_element)
                else:
                    flush_paragraph_run()
                    flush_list_run()
                    recovered.extend(nested)
        else:
            flush_paragraph_run()
            flush_list_run()
            recovered.append(element)

    for element in elements:
        consume(element)

    flush_paragraph_run()
    flush_list_run()
    return recovered


def _attach_paragraph_to_pending_item(
    paragraph: Paragraph,
    list_run: list[ListItem],
    *,
    base_indent: int,
) -> bool:
    """Attach one paragraph to the current list item when nested by indent."""
    if not list_run:
        return False

    paragraph_indent = _indent_width(paragraph.indent)
    if paragraph.indent is None:
        paragraph_indent = base_indent
    if paragraph_indent <= base_indent:
        return False

    list_run[-1].append_body(paragraph, mark_dirty=False)
    return True


def _attach_block_to_pending_item(
    block: IndentBlock,
    list_run: list[ListItem],
    *,
    parent: Document | Heading | Element | None,
    base_indent: int,
) -> bool:
    """Attach one block's recovered body to the current list item when nested."""
    if not list_run:
        return False

    block_indent = _indent_width(block.indent)
    if block.indent is None:
        block_indent = base_indent
    if block_indent <= base_indent:
        return False

    recovered = _recover_stream(
        block.body,
        parent=parent,
        in_block=True,
        base_indent=block_indent,
    )
    for nested in recovered:
        list_run[-1].append_body(nested, mark_dirty=False)
    return True


def _merge_paragraphs(
    paragraphs: list[Paragraph],
    *,
    parent: Document | Heading | Element | None,
) -> Paragraph:
    """Merge consecutive paragraph elements into one source-preserving object."""
    merged_text = "".join(_elem_source_text(p) for p in paragraphs)
    return Paragraph(
        body=RichText(merged_text),
        indent=paragraphs[0].indent,
        parent=parent,
    )


def _elem_source_text(element: Element) -> str:
    """Return the verbatim source text for one parse-backed element.

    Returns an empty string for programmatically constructed elements that
    have no backing node or document.
    """
    return node_source(element._node, element._document)


def _indent_width(indent: str | None) -> int:
    """Return indentation width for one optional indent string."""
    if indent is None:
        return 0
    width = 0
    for char in indent:
        if char == " ":
            width += 1
            continue
        if char == "\t":
            # Org Mode (Emacs) treats a tab as 8 display columns, matching
            # the default tab-width used when computing list indentation.
            width += 8
            continue
        break
    return width
