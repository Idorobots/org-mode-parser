# Plan: Logbook / Drawer Indent Blocks

**Status**: Ready to implement  
**Failing test**: `tests/test_repeat_elements.py::test_repeat_uses_entire_item_body_as_note_payload`

---

## Problem

Indented continuation lines inside a drawer body are not wrapped in `block` nodes.

```
:LOGBOOK:
- State "CANCELLED"  from "TODO"       [2025-07-28 pon 18:41] \\
  No need to.
- State "DONE"       from "TODO"       [2025-07-28 pon 18:33]
:END:
```

`  No need to.` should be in a `block` sibling of the `list_item`, mirroring how
the same list parses *outside* a drawer.  Currently the indented paragraph becomes
a direct `body` child of `logbook_drawer` with no `IndentBlock` wrapper, so the
Python list-recovery layer rejects it when trying to attach it to the preceding
list item.

### Root cause — grammar

`_drawer_body_line` uses `optional($._INDENT)` (the regex `/[ \t]+/`) to consume
leading whitespace:

```js
_drawer_body_line: $ => choice(
  $.blank_line,
  $._drawer_timestamp_line,
  seq(optional($._INDENT), choice(
    $.drawer_kv_line,
    $.drawer_double_colon_line,
    $._drawer_element,
  )),
),
```

`$._INDENT` is a plain regex token — it is never `$._BLOCK_BEGIN` — so
`TOKEN_BLOCK_BEGIN` is never in `valid_symbols` inside a drawer body.  The
external scanner's `scan_block_begin` is never called, no `block` node is
produced, and the whitespace is simply consumed and discarded.

### Root cause — Python

`_attach_paragraph_to_pending_item` in `_list_recovery.py` checks:

```python
paragraph_indent = _indent_width(paragraph.indent)
if paragraph.indent is None:
    paragraph_indent = base_indent   # 0
if paragraph_indent <= base_indent:  # 0 <= 0 → True
    return False
```

`paragraph.indent` is `None` because there is no `IndentBlock` wrapping.  The
paragraph is emitted as a standalone element instead of being attached to the
list item's body.  Consequently `repeat.body` is empty.

---

## Solution

### Change 1 — `tree-sitter-org/grammar.js`

Add `$.block` as a valid alternative in `_drawer_body_line`:

```js
_drawer_body_line: $ => choice(
  $.blank_line,
  $._drawer_timestamp_line,
  $.block,          // NEW: allow indented content blocks inside drawers
  seq(optional($._INDENT), choice(
    $.drawer_kv_line,
    $.drawer_double_colon_line,
    $._drawer_element,
  )),
),
```

With `$.block` present, `TOKEN_BLOCK_BEGIN` becomes a valid symbol at the start
of each drawer body line.  `scan_block_begin` fires for any line indented beyond
the current block depth, producing a proper `block` node.  `TOKEN_BLOCK_END`
fires naturally when a subsequent line has lower indentation — which covers the
normal case (`:END:` at col 0 after continuation at col 2).

The `block` rule body uses `$._section_element_no_block`.  This includes
`paragraph`, `list_item`, and all other section-level elements.  It also
technically allows nested drawers inside the block; this is an unlikely edge
case and acceptable given the architectural simplicity it preserves.

### Change 2 — `tree-sitter-org/src/scanner.c`

**The "mis-aligned archive style" problem.**  Emacs' archiving produces logbooks
where `:END:` is indented to the *same* column as the indented content:

```
:LOGBOOK:
- State "DONE" ...          ← col 0
    - State "CANCELLED" ... ← col 4  → _BLOCK_BEGIN fires, opens block
    :END:                   ← col 4  = current → _BLOCK_END currently won't fire
```

`scan_block_end` only closes when `indent_col < current`.  After Change 1 the
block opened at col 4 would never close, and `:END:` would be fed into
`_section_element_no_block` causing a parse failure.

**Fix**: in `scan_block_end`, add a `:end:` lookahead when
`indent_col == current`.  All advances happen *after* `mark_end(lexer)` (the
token is zero-width), so the characters peeked are not consumed.

Replace the final `should_close` block:

```c
// Before:
bool should_close = false;
if (eof(lexer)) { should_close = true; }
else if (indent_col < current) { should_close = true; }
if (!should_close) return -1;
```

```c
// After:
bool should_close = false;
if (eof(lexer)) { should_close = true; }
else if (indent_col < current) { should_close = true; }
else if (indent_col == current && ch == ':') {
  /* Peek for ':end:' case-insensitively without consuming (mark_end already
   * called above, so these advances don't extend the zero-width token). */
  advance(lexer); int32_t c2 = lookahead(lexer);
  if (c2 == 'e' || c2 == 'E') {
    advance(lexer); int32_t c3 = lookahead(lexer);
    if (c3 == 'n' || c3 == 'N') {
      advance(lexer); int32_t c4 = lookahead(lexer);
      if (c4 == 'd' || c4 == 'D') {
        advance(lexer); int32_t c5 = lookahead(lexer);
        if (c5 == ':') { should_close = true; }
      }
    }
  }
}
if (!should_close) return -1;
```

**Risk**: In a section `block` where a content line happens to start with `:end:`
at the exact same indent level as the block, this would also close the block.
In practice `:end:` as meaningful *content* at the same column is vanishingly
rare; it is a drawer-termination keyword.

### Change 3 — `tree-sitter-org/test/corpus/drawers.txt`

Three existing tests need updated expected trees, and one new test is added.

#### 3a. "Custom drawer with indented timestamp line"

Input: `:PROGRESS:` at col 0, content `  [2025-01-06 Mon] …` at col 2.  
`_BLOCK_BEGIN` fires (2 > 0), wrapping the paragraph in a `block`.

Old body:
```
body: (paragraph (timestamp …) (plain_text) (newline))
```
New body:
```
body: (block
  indent: (indent)
  body: (paragraph (timestamp …) (plain_text) (newline)))
```

#### 3b. "LOGBOOK drawer with mis-aligned end in archive style"

Four indented items/paragraphs at col 4 become a single `block` node.  The
continuation at col 6 becomes a nested `block` inside.

Old body: four direct paragraph siblings.  
New body: `list_item` at col 0 + one `block` containing:
- `list_item` (the `- State "CANCELLED"` entry)
- inner `block` containing the continuation paragraph
- two more `list_item`s

#### 3c. "Indented LOGBOOK drawer with note line"

The continuation paragraph `      No need to.` at col 6 (inside an indented
logbook at col 4) was a direct `logbook_drawer` body sibling.  Now it is wrapped
in a `block`.

Old body:
```
body: (list_item …)
body: (paragraph (plain_text) (newline))
```
New body:
```
body: (list_item …)
body: (block
  indent: (indent)
  body: (paragraph (plain_text) (newline)))
```

#### 3d. New test: unindented logbook with continuation note

```
================
Unindented LOGBOOK drawer with note continuation
================
* H
:LOGBOOK:
- State "CANCELLED"  from "TODO"       [2026-03-08 Sun 13:18] \\
  No need to.
:END:

---

(document
  (heading
    stars: (stars)
    title: (plain_text)
    body: (section
      (logbook_drawer
        body: (list_item
          first_line: (plain_text)
          first_line: (timestamp …)
          first_line: (plain_text)
          first_line: (line_break))
        body: (block
          indent: (indent)
          body: (paragraph
            (plain_text)
            (newline)))))))
```

---

## What does NOT change

- **No Python code changes.**  `_extract_drawer_body_element` in `_drawer.py`
  already dispatches `block` nodes to `_extract_indent_block`, creating
  `IndentBlock` objects.  `recover_lists` in `_list_recovery.py` already handles
  `IndentBlock` via `_attach_block_to_pending_item`, which recursively attaches
  the block body to the last pending `ListItem`.

- **`lists.txt`** — no list corpus tests are affected (the grammar change only
  applies to `_drawer_body_line`).

- **Python quality gate** — `poetry run task check` must pass in full after the
  changes; specifically `test_repeat_uses_entire_item_body_as_note_payload` must
  now pass.

---

## Why `$.block` (not a new `_drawer_block`)

A dedicated `_drawer_block` rule using `$._drawer_element` as its body would be
more restrictive (correctly excluding nested drawers from block bodies).  However
it would require:

- A new public or alias'd grammar rule
- Duplication of the `block` rule's indent/body/repeat/end structure
- Ensuring the Python `BLOCK` dispatch constant recognises the new node type, or
  aliasing to `$.block`

Given that the only realistic body content of a drawer continuation block is
`paragraph` (and occasionally `list_item` or `clock`), all of which are in both
`_section_element_no_block` and `_drawer_element`, reusing `$.block` directly
is correct for all practical inputs.

---

## Build / test sequence

```bash
# 1. Rebuild grammar artifacts
cd tree-sitter-org
npm run build          # tree-sitter generate + node-gyp build
tree-sitter build      # refreshes org.so for the Python library

# 2. Run tree-sitter corpus tests
tree-sitter test

# 3. Check example files
cd ..
python3 check.py "examples/*.org" "*.org"

# 4. Full Python quality gate (must include the previously-failing test)
poetry run task check
```
