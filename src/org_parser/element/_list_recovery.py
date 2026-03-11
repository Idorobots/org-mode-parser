"""Semantic recovery helpers for list and block structure."""

from __future__ import annotations

from typing import TYPE_CHECKING

from org_parser.element._indent_block import IndentBlock
from org_parser.element._list import List, ListItem
from org_parser.element._paragraph import Paragraph
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


def _recover_stream(
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

    for element in elements:
        if element.node_type == "blank_line":
            flush_paragraph_run()
            if in_block:
                flush_list_run()
                recovered.append(element)
                continue

            if list_run:
                continue

            recovered.append(element)
            continue

        if isinstance(element, ListItem):
            flush_paragraph_run()
            list_run.append(element)
            continue

        if in_block and isinstance(element, Paragraph):
            flush_list_run()
            paragraph_run.append(element)
            continue

        if isinstance(element, IndentBlock):
            attached = _attach_block_to_pending_item(
                element,
                list_run,
                parent=parent,
                base_indent=base_indent,
            )
            if attached:
                continue

            flush_paragraph_run()
            flush_list_run()
            recovered.extend(
                _recover_stream(
                    element.body,
                    parent=parent,
                    in_block=True,
                    base_indent=_source_indent_width(element.source_text),
                )
            )
            continue

        flush_paragraph_run()
        flush_list_run()
        recovered.append(element)

    flush_paragraph_run()
    flush_list_run()
    return recovered


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

    item = list_run[-1]
    item_indent = base_indent + _source_indent_width(item.source_text)
    block_indent = _source_indent_width(block.source_text)
    if block_indent <= item_indent:
        return False

    recovered = _recover_stream(
        block.body,
        parent=parent,
        in_block=True,
        base_indent=block_indent,
    )
    for nested in recovered:
        item.append_body(nested, mark_dirty=False)
    return True


def _merge_paragraphs(
    paragraphs: list[Paragraph],
    *,
    parent: Document | Heading | Element | None,
) -> Paragraph:
    """Merge consecutive paragraph elements into one source-preserving object."""
    merged_text = "".join(paragraph.source_text for paragraph in paragraphs)
    return Paragraph(
        body=RichText(merged_text),
        indent=paragraphs[0].indent,
        parent=parent,
        source_text=merged_text,
    )


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
            width += 1
            continue
        break
    return width


def _source_indent_width(source_text: str) -> int:
    """Return indentation width from the first non-empty source line."""
    for line in source_text.splitlines():
        if line.strip() == "":
            continue
        return _indent_width(line)
    return 0
