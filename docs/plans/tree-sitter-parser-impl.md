# Tree-sitter Parser Implementation Plan

> Implementation plan for the `tree-sitter-org` parser, based on the
> formal grammar in [`syntax.md`](syntax.md).

---

## Table of Contents

1. [Overview](#1-overview)
2. [Project Layout](#2-project-layout)
3. [Phase 1 — Scaffold & Tooling](#3-phase-1--scaffold--tooling)
4. [Phase 2 — Core Grammar](#4-phase-2--core-grammar)
5. [Phase 3 — External Scanner](#5-phase-3--external-scanner)
6. [Phase 4 — Error Recovery](#6-phase-4--error-recovery)
7. [Phase 5 — Test Corpus](#7-phase-5--test-corpus)
8. [Phase 6 — Integration Testing](#8-phase-6--integration-testing)
9. [Risks & Tradeoffs](#9-risks--tradeoffs)
10. [Estimated Scope](#10-estimated-scope)
11. [Open Questions](#11-open-questions)

---

## 1. Overview

Build a tree-sitter grammar (`tree-sitter-org`) implementing the formal
PEG specification from `docs/plans/syntax.md`. The parser is a
standalone tree-sitter project that will later be embedded in Python via
`py-tree-sitter`.

Key requirements:

- **Source location preservation** — every parsed node retains its byte
  range so the original content can be reconstructed from the tree.
- **Error recovery** — descriptive parse error messages; invalid content
  degrades gracefully into `ERROR` / paragraph nodes rather than
  crashing the parse.
- **External scanner** (C) — handles context-sensitive features that
  tree-sitter's grammar DSL cannot express (heading levels, list
  indentation, TODO keyword tracking, markup lookbehind, etc.).

---

## 2. Project Layout

```
tree-sitter-org/
├── grammar.js              # Main tree-sitter grammar
├── src/
│   └── scanner.c           # External scanner (C)
├── queries/
│   └── highlights.scm      # Basic highlight queries (useful for testing)
├── test/
│   └── corpus/             # Tree-sitter test corpus (txt files)
│       ├── document.txt
│       ├── headings.txt
│       ├── sections.txt
│       ├── greater_blocks.txt
│       ├── lesser_blocks.txt
│       ├── drawers.txt
│       ├── lists.txt
│       ├── tables.txt
│       ├── planning.txt
│       ├── comments.txt
│       ├── keywords.txt
│       ├── objects.txt
│       ├── timestamps.txt
│       ├── links.txt
│       ├── markup.txt
│       ├── footnotes.txt
│       ├── citations.txt
│       └── error_recovery.txt
├── package.json
├── binding.gyp
└── bindings/
    └── node/               # Node.js bindings (auto-generated)
```

---

## 3. Phase 1 — Scaffold & Tooling

1. **Initialize the tree-sitter project** in `tree-sitter-org/` using
   `npm init` and install `tree-sitter-cli` as a dev dependency.
2. **Create `package.json`** with tree-sitter metadata (language name,
   scope, file-types `.org`).
3. **Create a minimal `grammar.js`** that parses
   `document <- _anything*` to verify the toolchain works
   (`tree-sitter generate && tree-sitter parse`).

---

## 4. Phase 2 — Core Grammar

Build the grammar incrementally, starting from document structure and
working inward. Each rule maps directly from the PEG spec (§1.4 mapping
table in `syntax.md`).

### 4a. Document Structure (syntax.md §2)

- `document` → `zeroth_section? heading*`

### 4b. Headings (syntax.md §3)

- `heading`, `stars`, `todo_keyword`, `priority`, `tags`, `tag`
- Heading nesting managed by external scanner (Phase 3).
- Field labels: `stars`, `todo`, `priority`, `is_comment`, `title`,
  `tags`, `planning`, `properties`, `body`.

### 4c. Sections (syntax.md §4)

- `zeroth_section` — special keywords, comments, property drawer,
  elements.
- `section` — element sequence inside a heading.

### 4d. Element Dispatch (syntax.md §5)

- `_section_element`, `_zs_element` as `choice(...)` with `prec()`
  ordering.
- `paragraph` gets `prec(-1)` as the catch-all.
- `_affiliatable` / `_non_affiliatable` grouping.

### 4e. Greater Elements (syntax.md §6)

- Greater blocks: `center_block`, `quote_block`, `special_block`.
- `drawer`, `dynamic_block`, `footnote_definition`.
- `plain_list`, `item` (bullet variants, checkbox, item_tag,
  counter_set).
- `property_drawer`, `node_property`.
- `org_table`, `tableel_table`, `table_row`, `table_cell`.

### 4f. Lesser Elements (syntax.md §7)

- Lesser blocks: `comment_block`, `example_block`, `export_block`,
  `src_block`, `verse_block`.
- `clock`, `diary_sexp`, `planning`.
- `comment`, `fixed_width`, `horizontal_rule`.
- `special_keyword`, `caption_keyword`.
- `paragraph` (catch-all).

### 4g. Objects (syntax.md §8)

- `export_snippet`, `footnote_reference`, `citation`,
  `citation_reference`.
- `inline_source_block`, `line_break`.
- Links: `regular_link`, `angle_link`, `plain_link`, `radio_link`.
- `target`, `radio_target`.
- `timestamp` (active, inactive, ranges, same-day ranges).
- Text markup: `bold`, `italic`, `underline`, `strike_through`,
  `verbatim`, `code`.
- `plain_text`.

### 4h. Object Sets (syntax.md §9)

- `_object`, `_object_nolb`, `_object_nofn`, `_object_min`,
  `_object_table` as separate `choice()` rules.

### 4i. Lexical Primitives (syntax.md §10)

- `_NL`, `_S`, `_INDENT`, `_TRAILING`, `_REST_OF_LINE`, `_blank_line`.
- Balanced constructs via external scanner.

### Key `grammar.js` Design Decisions

| Decision | Rationale |
|----------|-----------|
| `prec()` / `prec.left()` / `prec.right()` | Resolve ambiguities (paragraph lowest, headings highest). |
| `field('name', ...)` | All labeled children per the spec for easy downstream access. |
| `alias()` | Where hidden rules need named CST nodes. |
| `_` prefix for hidden rules | Standard tree-sitter convention. |
| `token()` / `token.immediate()` | Tight token boundaries (e.g., `'#+begin_'` as a single token). |
| `$.EXTERNAL_TOKEN` references | For scanner-emitted tokens. |

---

## 5. Phase 3 — External Scanner

The scanner handles context-sensitive parsing that tree-sitter's grammar
DSL cannot express (syntax.md §12).

### 5a. Scanner State & Serialization

| State | Purpose |
|-------|---------|
| Heading level stack | Track nesting depth for heading containment. |
| List indentation stack | Group items by indentation level. |
| TODO keyword set | Mutable; initially `["TODO", "DONE"]`. |
| Block name stack | Match `#+end_NAME` to `#+begin_NAME`. |
| Previous character | Markup lookbehind (PRE constraint). |
| Consecutive blank line counter | Two-blank-line termination of items/fndefs. |

All state must be serializable for tree-sitter's incremental parsing to
work correctly.

### 5b. External Tokens

Declared in `grammar.js`'s `externals` array:

| Token | Description |
|-------|-------------|
| `_HEADING_END` | Close a heading when same-or-higher-level stars found or EOI. |
| `_LIST_START` / `_LIST_END` | Bracket a plain list at one indentation level. |
| `_ITEM_END` | Terminate a list item (indent/blank-line rules). |
| `_TODO_KW` | Matches current TODO keyword set. |
| `_BLOCK_END_MATCH` | Verify `#+end_NAME` matches `#+begin_NAME`. |
| `_GBLOCK_NAME` | Block name that is NOT a lesser block name. |
| `_MARKUP_OPEN_*` | Markup opening markers with PRE lookbehind check. |
| `_MARKUP_CLOSE_*` | Markup closing markers with POST lookahead check. |
| `_BOL` | Beginning-of-line token with column tracking. |
| `_PARAGRAPH_CONTINUE` | Emitted when next line doesn't start an element. |
| `_FNDEF_END` | Footnote definition termination. |
| `_PLAIN_TEXT` | Scan forward to next object boundary. |
| `_ITEM_TAG_END` | Rightmost ` :: ` detection. |

### 5c. Scanner Functions

```c
void *tree_sitter_org_external_scanner_create();
void  tree_sitter_org_external_scanner_destroy(void *payload);
unsigned tree_sitter_org_external_scanner_serialize(void *payload, char *buffer);
void  tree_sitter_org_external_scanner_deserialize(void *payload, const char *buffer, unsigned length);
bool  tree_sitter_org_external_scanner_scan(void *payload, TSLexer *lexer, const bool *valid_symbols);
```

### 5d. Key Algorithms

- **Heading level tracking** — Push level on heading entry; pop when
  `*`-count <= top of stack or EOI. Emit `_HEADING_END`.
- **List indentation** — Push indent on item start; pop when indent <=
  top. Track two-blank-line termination.
- **TODO keyword update** — When `#+TODO:` is parsed, parse the value
  and update the keyword set before continuing.
- **Block matching** — Push block name on `#+begin_`; match and pop on
  `#+end_`.
- **Markup lookbehind** — Track previous character; emit markup open
  only if prev char is in PRE set `[ \t\-({'"]` or BOL.
- **Paragraph termination** — Check element-start patterns at line
  boundaries.

---

## 6. Phase 4 — Error Recovery

Tree-sitter provides built-in error recovery via the `ERROR` node. We
enhance it with the following strategies:

| Strategy | Detail |
|----------|--------|
| **`extras` array** | Include `_NL` and `_S` so whitespace is handled gracefully during error recovery. |
| **Strategic `prec()` assignments** | Lower-precedence rules (paragraph) absorb unrecognized content rather than producing errors. |
| **Unclosed block recovery** | If `#+end_NAME` is missing, the scanner gracefully closes the block at the next heading or EOI. |
| **Mismatched blocks** | When `#+end_NAME` doesn't match `#+begin_NAME`, produce an `ERROR` node but continue parsing. |
| **Unclosed markup** | If closing marker isn't found on the same line, treat the opening marker as plain text. |
| **Fallback to paragraph** | Any unrecognized content becomes paragraph text via `prec(-1)`. |

---

## 7. Phase 5 — Test Corpus

Tree-sitter uses a specific test format in `test/corpus/*.txt`:

```
================
Test Name
================

input content

---

(expected_tree)
```

Create tests for every named node type (syntax.md Appendix A):

| Category | Coverage |
|----------|----------|
| Document structure | Empty document, zeroth-section only, headings only, mixed. |
| Headings | All field combinations, nested levels, TODO keywords, priorities, tags, COMMENT token. |
| Sections | Zeroth section with keywords/properties, normal sections. |
| Greater blocks | center, quote, special; nested content; parameters. |
| Lesser blocks | comment, example, export, src (with switches), verse. |
| Drawers | Basic, property drawer positions, content. |
| Lists | All bullet types, ordered/unordered/descriptive, checkboxes, nesting, counter-set, two-blank-line termination. |
| Tables | Org-type (standard rows, rule rows, TBLFM), table.el-type. |
| Objects | All 19+ object types individually and in combination. |
| Error recovery | Unclosed blocks, mismatched blocks, invalid markup, malformed timestamps. |

---

## 8. Phase 6 — Integration Testing

1. **Parse all example files** with `tree-sitter parse examples/*.org`
   — verify no crashes and reasonable trees.
2. **Check source location preservation** — verify every leaf node's
   byte range concatenation reconstructs the original file.
3. **Error count check** — files that are valid org should produce zero
   `ERROR` nodes.

---

## 9. Risks & Tradeoffs

| Issue | Decision |
|-------|----------|
| **Radio links require two-pass parsing** | Defer radio link detection (syntax.md §12.10) — emit `radio_target` nodes, but radio link matching is a post-processing step in Python. The grammar defines the node type but the scanner won't auto-detect occurrences. |
| **TODO keyword dynamism** | Implement in scanner with mutable keyword list. Serialization includes the keyword set for incremental parsing correctness. |
| **Scanner complexity** | The scanner is the largest risk area. Keep it well-structured with separate handler functions per token type. |
| **Markup ambiguity** | Markup lookbehind/lookahead via scanner. If matching fails, fall back to `plain_text` gracefully. |
| **Grammar size** | Org is a large grammar. tree-sitter can handle it but generation time may be 10–30 s. |
| **Plain text performance** | The scanner emits `plain_text` tokens by scanning forward to the next potential object start, avoiding character-by-character matching. |

---

## 10. Estimated Scope

| Component | Lines of code (approx.) |
|-----------|------------------------|
| `grammar.js` | 600–800 |
| `src/scanner.c` | 1200–1800 |
| Test corpus | 2000–3000 |
| **Total** | **4000–5500** |

---

## 11. Open Questions

### 11.1 Radio Links

The spec says radio links require a pre-pass to collect all radio
targets. This is fundamentally at odds with single-pass tree-sitter
parsing. Proposed resolution: define the `radio_link` node type in the
grammar but **defer detection to the Python layer** — the tree-sitter
parse emits `radio_target` nodes, and Python code does the
text-matching pass afterward.

### 11.2 Incremental Development Strategy

Build and test incrementally — scaffold first, then document structure +
headings, then elements, then objects. Early phases produce a working
parser that treats unimplemented elements as paragraph text,
progressively improving.

### 11.3 Project Location

The parser lives in `tree-sitter-org/` at the repository root.
