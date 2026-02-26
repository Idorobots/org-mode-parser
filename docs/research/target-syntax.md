# Target Syntax

> A defined subset of Org Mode syntax targeted by this parser.
> Self-contained; see [`syntax.md`](syntax.md) for the full specification.

---

## Table of Contents

1. [Scope](#1-scope)
2. [Document Structure](#2-document-structure)
3. [Elements](#3-elements)
   - 3.1 [Headings](#31-headings)
   - 3.2 [Sections](#32-sections)
   - 3.3 [Greater Elements](#33-greater-elements)
   - 3.4 [Lesser Elements](#34-lesser-elements)
4. [Objects](#4-objects)
5. [Containment Rules](#5-containment-rules)
6. [Configurable Behaviour](#6-configurable-behaviour)
7. [Parser Notes](#7-parser-notes)

---

## 1. Scope

### 1.1 Inclusions and Exclusions

The following features are **explicitly excluded**:

| Excluded feature | Syntax affected |
|---|---|
| Inlinetasks | Headings with ≥ `org-inlinetask-min-level` stars behave as ordinary headings |
| Arbitrary keywords | `#+KEY: VALUE` is not parsed; only `#+CAPTION:` (affiliated) and special keywords are recognised |
| LaTeX environments | `\begin{...}...\end{...}` is treated as plain text |
| LaTeX fragments | `\(`, `\[`, `$$`, `$x$` forms are treated as plain text |
| Babel (`#+call:`) | `#+call:` keyword is not parsed |
| Inline Babel calls | `call_NAME(...)` objects are treated as plain text |
| Entities | `\alpha`, `\cent`, etc. are treated as plain text |
| Macros | `{{{name}}}` is treated as plain text |
| Statistics cookies | `[33%]`, `[1/3]` are treated as plain text |
| Subscript & superscript | `x^2`, `A_i` are treated as plain text |
| Sexp timestamps | `<%%(SEXP)>` timestamp subtype is not parsed |

Everything not listed above is **in scope**, including: all block types, drawers, plain lists, tables, footnotes, citations, export snippets, inline source blocks, links, timestamps (active/inactive/range), and all six text markup types.

### 1.2 Keyword Scope

Two keyword categories are in scope:

- **Special keywords** — file-level metadata (`#+TITLE:`, `#+AUTHOR:`, etc.). Recognised only in the zeroth section.
- **`#+CAPTION:`** — as an affiliated keyword, immediately preceding an affiliatable element.

All other `#+KEY: VALUE` patterns are unrecognised and not part of the tree.

---

## 2. Document Structure

An Org document is a tree rooted at an implicit document node.

```
document
├── zeroth-section (optional)
│   ├── special-keyword*
│   ├── comment*
│   ├── property-drawer (optional)
│   └── element*
└── heading*
    ├── section (optional)
    │   └── element*
    └── heading*  (sub-headings, recursively)
```

**Rules:**

- The **zeroth section** contains everything before the first heading. It may hold special keywords, comments, and a property drawer. It **cannot** contain planning.
- A **heading** optionally owns a section followed by zero or more sub-headings at any greater depth.
- A **section** ends at the next heading at the same or higher level, or at end of document.
- Blank lines immediately following a heading's stars line are not part of the section.

---

## 3. Elements

### 3.1 Headings

An **unindented** line:

```
STARS KEYWORD PRIORITY COMMENT TITLE TAGS
```

| Field | Rule |
|-------|------|
| `STARS` | One or more `*` followed by a space. Count = nesting level. |
| `KEYWORD` (optional) | A member of `org-todo-keywords-1`. Case-significant. |
| `PRIORITY` (optional) | `[#X]` — `X` is `A`–`Z` or an integer `0`–`64`. |
| `COMMENT` (optional) | The literal string `COMMENT`. Case-significant. Marks the heading as commented. |
| `TITLE` (optional) | Supported objects (see [§4](#4-objects)), excluding line breaks. |
| `TAGS` (optional) | `:tag1:tag2:` — each tag is `[A-Za-z0-9_@#%]+`. |

**Semantic flags:**

- Has `COMMENT` → heading is *commented*.
- `TITLE` equals `org-footnote-section` (default `"Footnotes"`) → *footnote section*. Case-significant.
- `ARCHIVE` is among the tags → heading is *archived*. Case-significant.

**Note on inlinetasks:** with the `org-inlinetask` library absent (the default for this parser), all star counts produce ordinary headings.

---

### 3.2 Sections

A section contains one or more non-heading elements.

- **Zeroth section** — before the first heading; may hold special keywords, comments, and a property drawer; cannot hold planning.
- **Normal section** — inside a heading; may hold any element except planning and property drawers at the top level (those attach directly to the heading).

---

### 3.3 Greater Elements

Greater elements can contain greater or lesser elements, subject to:

- No element of its own type (no nesting of the same kind).
- Planning only inside headings.
- Property drawers only in headings or the zeroth section.
- Node properties only inside property drawers.
- Items only inside plain lists.
- Table rows only inside tables.

---

#### 3.3.1 Greater Blocks

```
#+begin_NAME PARAMETERS
CONTENTS
#+end_NAME
```

`NAME` must not be a lesser block name (`comment`, `example`, `export`, `src`, `verse`).

| `NAME` | Subtype |
|--------|---------|
| `center` | center block |
| `quote` | quote block |
| any other | special block |

`PARAMETERS` (optional) — any characters except newline.  
`CONTENTS` — zero or more elements; no line may begin with `#+end_NAME`.

---

#### 3.3.2 Drawers

```
:NAME:
CONTENTS
:end:
```

`NAME` — `[A-Za-z0-9_-]+`.  
`CONTENTS` — zero or more elements, no nested drawer.  
`:end:` is case-insensitive.

---

#### 3.3.3 Dynamic Blocks

```
#+begin: NAME PARAMETERS
CONTENTS
#+end:
```

`NAME` — non-whitespace characters.  
`PARAMETERS` (optional) — any characters except newline.  
`CONTENTS` — zero or more elements, no nested dynamic block.

---

#### 3.3.4 Footnote Definitions

Must start at an **unindented** line:

```
[fn:LABEL] CONTENTS
```

`LABEL` — digits, or `[A-Za-z0-9_-]+`.  
`CONTENTS` — zero or more elements; ends at the next footnote definition, next heading, two consecutive blank lines, or end of buffer.

---

#### 3.3.5 Items

```
BULLET COUNTER-SET CHECK-BOX TAG CONTENTS
```

| Field | Rule |
|-------|------|
| `BULLET` | `*`, `-`, or `+`; or `COUNTER.` / `COUNTER)` where `COUNTER` is digits or a single letter `a`–`z`. Followed by whitespace or end of line. `*` at column 0 is always a heading. |
| `COUNTER-SET` (optional) | `[@COUNTER]` — resets the ordered list counter. |
| `CHECK-BOX` (optional) | `[ ]` unchecked, `[X]` checked, `[-]` partial. |
| `TAG` (optional) | `TAG-TEXT ::` — text up to the last ` :: ` on the line; parsed with supported objects. |
| `CONTENTS` (optional) | Zero or more elements; ends at next item, first line indented ≤ starting line (outside nested elements), or two consecutive blank lines. |

---

#### 3.3.6 Plain Lists

A sequence of consecutive items at the same indentation level. Items may contain nested plain lists.

| Condition | List type |
|-----------|-----------|
| First bullet has a `COUNTER` | ordered |
| First item has a `TAG` | descriptive |
| Otherwise | unordered |

---

#### 3.3.7 Property Drawers

```
:properties:
CONTENTS
:end:
```

Valid positions only:
- Directly after a heading (no blank lines), or
- After a heading's planning line (no blank lines), or
- In the zeroth section (after optional blank lines and comments).

`CONTENTS` — zero or more node properties, no blank lines between them.

---

#### 3.3.8 Tables

**Org-type table** — starts with `|`:

```
| cell | cell |
|------+------|
| cell | cell |
#+TBLFM: FORMULAS
```

Contains table rows. Ends at first line not starting with `|`. May be followed by `#+TBLFM: FORMULAS` lines.

**Table.el-type table** — starts with `+-`:

```
+------+-----+
| cell | cell |
+------+-----+
```

Parsed as a raw block. Ends at first line not starting with `|` or `+`. Does not contain structured table rows.

---

### 3.4 Lesser Elements

Lesser elements cannot contain other elements. Of those below, only **verse blocks**, **paragraphs**, and **table rows** can contain objects.

---

#### 3.4.1 Blocks

```
#+begin_NAME DATA
CONTENTS
#+end_NAME
```

`NAME` must be one of (case-insensitive):

| `NAME` | Subtype | `CONTENTS` |
|--------|---------|------------|
| `comment` | comment block | Raw string, not parsed |
| `example` | example block | Raw string, not parsed |
| `export` | export block | Raw string, not parsed; `DATA` is mandatory (single word: the backend) |
| `src` | source block | Raw string, not parsed; `DATA` is `LANGUAGE SWITCHES ARGUMENTS` |
| `verse` | verse block | Parsed as supported objects |

**Source block `DATA`:**

```
LANGUAGE SWITCHES ARGUMENTS
```

`LANGUAGE` — non-whitespace characters.  
`SWITCHES` (optional) — space-separated tokens from: `-l "FORMAT"`, `+n NUMBER`, `-n NUMBER`, `-r`, `-i`, `-k`.  
`ARGUMENTS` (optional) — any characters except newline.

**Comma-quoting:** lines inside block contents starting with `*` must be quoted `,*`; lines starting with `#+` may be quoted `,#+`. The parser strips leading commas from `,*` and `,#+` lines.

---

#### 3.4.2 Clock

```
CLOCK: INACTIVE-TIMESTAMP
CLOCK: INACTIVE-TIMESTAMP-RANGE DURATION
CLOCK: DURATION
```

`DURATION` — `=> HH:MM` (any-length `HH`, two-digit `MM`).  
`CLOCK:` is case-insensitive.

---

#### 3.4.3 Diary Sexp

Must start at an **unindented** line:

```
%%SEXP
```

`SEXP` starts with `(` and has balanced parentheses. Parsed as a raw string; not further decomposed.

---

#### 3.4.4 Planning

```
HEADING
PLANNING-LINE
```

`PLANNING-LINE` immediately follows `HEADING` with no blank lines. It contains one or more `KEYWORD: TIMESTAMP` pairs:

| `KEYWORD` | Meaning |
|-----------|---------|
| `DEADLINE` | Deadline |
| `SCHEDULED` | Scheduled date |
| `CLOSED` | Closed date |

If a keyword is repeated, the last instance wins. Timestamps here are standard active/inactive timestamps (no sexp form).

---

#### 3.4.5 Comments

One or more consecutive comment lines. A comment line starts with `#` followed by a space or end of line.

```org
# a comment
#
# multi-line
```

---

#### 3.4.6 Fixed-Width Areas

One or more consecutive fixed-width lines. A fixed-width line starts with `:` followed by a space or end of line.

```org
: verbatim line one
: verbatim line two
```

---

#### 3.4.7 Horizontal Rules

A line of at least five consecutive hyphens and nothing else:

```
-----
```

---

#### 3.4.8 Special Keywords

Recognised **only in the zeroth section**, these carry document-level metadata:

```
#+KEY: VALUE
```

`VALUE` is a raw string (not parsed as objects).

Recognised keys:

| Key | Meaning |
|-----|---------|
| `TITLE` | Document title |
| `AUTHOR` | Author name(s) |
| `DATE` | Document date |
| `EMAIL` | Author email |
| `DESCRIPTION` | Document description |
| `KEYWORDS` | Document keywords |
| `LANGUAGE` | Document language |
| `CATEGORY` | Default agenda category |
| `FILETAGS` | File-wide tags applied to all headings (`:tag1:tag2:` syntax) |
| `TAGS` | Global tag list / tag groups |
| `TODO` / `SEQ_TODO` / `TYP_TODO` | Custom TODO keyword sequences — updates `org-todo-keywords-1` for this file |
| `PRIORITIES` | Custom priority range |
| `PROPERTY` | File-level default property value |
| `STARTUP` | Initial display options |
| `ARCHIVE` | Default archive location |
| `COLUMNS` | Column view format |
| `OPTIONS` | Export and display flags |

Any `#+KEY: VALUE` in the zeroth section whose key matches this list is a special keyword. All others are not parsed.

Anywhere outside the zeroth section, `#+KEY: VALUE` patterns are not parsed (except `#+CAPTION:` as an affiliated keyword — see below, and `#+TBLFM:` which is part of a table).

---

#### 3.4.9 `#+CAPTION:` Affiliated Keyword

The only affiliated keyword in scope. Placed **immediately above** an affiliatable element (no blank line between):

```
#+CAPTION: VALUE
#+CAPTION[OPTVAL]: VALUE
```

`VALUE` — supported objects (excluding footnote references).  
`OPTVAL` (optional) — any characters except newline; balanced brackets. Used for a short caption.

Multiple `#+CAPTION:` lines before an element are concatenated. When no affiliatable element immediately follows, the line is not parsed.

Elements that **cannot** be affiliated: comments, clocks, headings, items, node properties, planning, property drawers, sections, table rows.

---

#### 3.4.10 Node Properties

Only inside property drawers:

```
:NAME: VALUE
:NAME:
:NAME+: VALUE
:NAME+:
```

`NAME` — non-empty, non-whitespace, not ending with `+`.  
`VALUE` (optional) — any characters except newline.  
`NAME+` form appends to an existing property rather than replacing it.

---

#### 3.4.11 Paragraphs

The default element — any content not matched by another element type. Terminated by blank lines or element boundaries. Contains supported objects.

---

#### 3.4.12 Table Rows

A line starting with `|`:

- `|` followed by cells → **standard** row.
- `|` followed by `-` (any non-newline characters may follow) → **rule** row (separator).

Only in Org-type tables.

---

## 4. Objects

Objects appear within element content. The supported object set is the full standard set minus: entities, LaTeX fragments, inline Babel calls, macros, statistics cookies, subscript, and superscript.

Explicitly supported:

| Object | Summary |
|--------|---------|
| [Export Snippets](#41-export-snippets) | `@@backend:value@@` |
| [Footnote References](#42-footnote-references) | `[fn:label]`, `[fn:label:def]`, `[fn::def]` |
| [Citations](#43-citations) | `[cite...:...]` |
| [Citation References](#44-citation-references) | `@key` within citations |
| [Inline Source Blocks](#45-inline-source-blocks) | `src_lang{body}` |
| [Line Breaks](#46-line-breaks) | `\\` at end of line |
| [Links](#47-links) | radio, plain, angle, regular |
| [Targets & Radio Targets](#48-targets-and-radio-targets) | `<<target>>`, `<<<radio>>>` |
| [Table Cells](#49-table-cells) | `content \|` |
| [Timestamps](#410-timestamps) | active, inactive, ranges |
| [Text Markup](#411-text-markup) | bold, italic, underline, verbatim, code, strike-through |
| [Plain Text](#412-plain-text) | fallthrough string |

Objects also appear in: heading and inlinetask `TITLE`, item `TAG`, `#+CAPTION:` values, verse block contents, and table cells.

---

### 4.1 Export Snippets

```
@@BACKEND:VALUE@@
```

`BACKEND` — `[A-Za-z0-9-]+`.  
`VALUE` (optional) — any characters not containing `@@`.

---

### 4.2 Footnote References

```
[fn:LABEL]
[fn:LABEL:DEFINITION]
[fn::DEFINITION]
```

`LABEL` — `[A-Za-z0-9_-]+`.  
`DEFINITION` — supported objects; balanced square brackets.

- Second form: *inline footnote*.
- Third form: *anonymous footnote*.
- First form on an **unindented** line is a **footnote definition** (element), not a reference.

---

### 4.3 Citations

```
[cite CITESTYLE: REFERENCES]
[cite CITESTYLE: GLOBALPREFIX;REFERENCES]
[cite CITESTYLE: REFERENCES;GLOBALSUFFIX]
[cite CITESTYLE: GLOBALPREFIX;REFERENCES;GLOBALSUFFIX]
```

`cite` and `CITESTYLE` are not separated by whitespace. Whitespace after the leading colon or before `]` is not significant.

| Field | Rule |
|-------|------|
| `CITESTYLE` (optional) | `/STYLE` or `/STYLE/VARIANT`. `STYLE` is `[A-Za-z0-9_-]+`. `VARIANT` is `[A-Za-z0-9_\-/]+`. |
| `GLOBALPREFIX` (optional) | Supported objects; balanced brackets; no `;` or `@KEY` subsequences. |
| `REFERENCES` | One or more citation reference objects separated by `;`. |
| `GLOBALSUFFIX` (optional) | Same rules as `GLOBALPREFIX`. |

---

### 4.4 Citation References

Only inside citations:

```
KEYPREFIX @KEY KEYSUFFIX
```

No whitespace between `KEYPREFIX`, `@KEY`, and `KEYSUFFIX`.

| Field | Rule |
|-------|------|
| `KEYPREFIX` (optional) | Minimal-set objects; balanced brackets; no `;` or `@KEY` subsequences. |
| `KEY` | `[A-Za-z0-9\-.:?!\`'/*@+|(){}><&_^$#%~]+` |
| `KEYSUFFIX` (optional) | Minimal-set objects; balanced brackets; no `;`. |

The **minimal object set** in this target syntax contains: plain text, text markup, export snippets, inline source blocks, line breaks, links, targets, radio targets, and timestamps. (Entities, LaTeX fragments, macros, statistics cookies, sub/superscript are excluded from the full minimal set.)

---

### 4.5 Inline Source Blocks

```
src_LANG{BODY}
src_LANG[HEADERS]{BODY}
```

`LANG` — characters excluding whitespace, `[`, and `{`.  
`HEADERS` (optional) — non-newline characters; balanced `[]`.  
`BODY` — non-newline characters; balanced `{}`.

---

### 4.6 Line Breaks

At the end of an otherwise non-blank line:

```
PRE\\SPACE
```

`PRE` — anything except `\`.  
`SPACE` — zero or more spaces/tabs.

---

### 4.7 Links

#### Radio Links

```
PRE RADIO POST
```

Auto-generated when a matching radio target exists. `RADIO` contains minimal-set objects.

`PRE` — non-alphanumeric or line-breakable character.  
`POST` — non-alphanumeric or line-breakable character.

#### Plain Links

```
PRE LINKTYPE:PATHPLAIN POST
```

`PRE` / `POST` — non-word-constituent character.  
`LINKTYPE` — member of `org-link-parameters` (default: `shell`, `news`, `mailto`, `https`, `http`, `ftp`, `help`, `file`, `elisp`).  
`PATHPLAIN` — non-whitespace, non-bracket characters; depth-2 parenthesised substrings permitted; must end with a non-punctuation non-whitespace character, `/`, or a parenthesised substring.

#### Angle Links

```
<LINKTYPE:PATHANGLE>
```

`PATHANGLE` — any characters except `>`; newlines and indentation ignored.

#### Regular Links

```
[[PATHREG]]
[[PATHREG][DESCRIPTION]]
```

`PATHREG` path types:

| Pattern | Type |
|---------|------|
| `FILENAME` | `file` |
| `LINKTYPE:PATHINNER` | `LINKTYPE` |
| `LINKTYPE://PATHINNER` | `LINKTYPE` |
| `id:ID` | `id` |
| `#CUSTOM-ID` | `custom-id` |
| `(CODEREF)` | `coderef` |
| `FUZZY` | `fuzzy` |

`PATHINNER`, `ID`, `CUSTOM-ID`, `CODEREF`, `FUZZY` — any characters except `[` and `]`.  
`\]` and `\\` are escapes inside `PATHREG`.  
Whitespace sequences inside `PATHREG` are normalised to a single space.

`DESCRIPTION` (optional) — minimal-set objects plus export snippets, inline source blocks; may include a plain or angle link; may contain `[` but not `]]`.

---

### 4.8 Targets and Radio Targets

**Target:**

```
<<TARGET>>
```

`TARGET` — any characters except `<`, `>`, `\n`; not starting or ending with whitespace.

**Radio target:**

```
<<<CONTENTS>>>
```

`CONTENTS` — minimal-set objects; starts and ends with non-whitespace; excludes `<`, `>`, `\n`. Defines an auto-link: every matching text occurrence in the document becomes a radio link.

---

### 4.9 Table Cells

```
CONTENTS SPACES|
CONTENTS SPACES END-OF-LINE
```

`CONTENTS` — objects not containing `|`: minimal-set objects plus citations, export snippets, footnote references, links, radio targets, targets, timestamps.  
`SPACES` — zero or more spaces (for column alignment).  
Final `|` may be omitted in the last cell of a row.

---

### 4.10 Timestamps

Sexp timestamps are excluded. Supported patterns:

```
<DATE TIME REPEATER-OR-DELAY>                                 active
[DATE TIME REPEATER-OR-DELAY]                                 inactive
<DATE TIME REPEATER-OR-DELAY>--<DATE TIME REPEATER-OR-DELAY>  active range (multi-day)
<DATE TIME-TIME REPEATER-OR-DELAY>                            active range (same-day)
[DATE TIME REPEATER-OR-DELAY]--[DATE TIME REPEATER-OR-DELAY]  inactive range (multi-day)
[DATE TIME-TIME REPEATER-OR-DELAY]                            inactive range (same-day)
```

**Fields:**

| Field | Pattern |
|-------|---------|
| `DATE` | `YYYY-MM-DD DAYNAME` — `DAYNAME` is optional non-whitespace excluding `+`, `-`, `]`, `>`, digits, `\n`. |
| `TIME` (optional) | `H:MM` — `H` is 1–2 digits, `MM` is exactly 2 digits. |
| `REPEATER-OR-DELAY` (optional) | Zero or one `REPEATER` and/or one `DELAY`, in any order, no whitespace between tokens. |

**Repeater:** `MARK VALUE UNIT` (or `MARK VALUE UNIT/VALUE UNIT` with upper bound)

| Token | Values |
|-------|--------|
| `MARK` | `+` cumulative, `++` catch-up, `.+` restart |
| `VALUE` | one or more digits |
| `UNIT` | `h` `d` `w` `m` `y` |

**Delay:** `MARK VALUE UNIT`

| Token | Values |
|-------|--------|
| `MARK` | `-` all, `--` first |
| `VALUE` | one or more digits |
| `UNIT` | `h` `d` `w` `m` `y` |

---

### 4.11 Text Markup

```
PRE MARKER CONTENTS MARKER POST
```

No whitespace between any of these tokens.

| Token | Values |
|-------|--------|
| `PRE` | Whitespace, `-`, `(`, `{`, `'`, `"`, or beginning of line |
| `POST` | Whitespace, `-`, `.`, `,`, `;`, `:`, `!`, `?`, `'`, `)`, `}`, `[`, `"`, `\`, or end of line |

Markup types:

| Marker | Type | Contents |
|--------|------|----------|
| `*` | bold | Supported objects |
| `/` | italic | Supported objects |
| `_` | underline | Supported objects |
| `=` | verbatim | Raw string (not parsed) |
| `~` | code | Raw string (not parsed) |
| `+` | strike-through | Supported objects |

`CONTENTS` must not start or end with whitespace.

---

### 4.12 Plain Text

Any string not matched by another object type. Whitespace within plain text is collapsed to a single space (`hello\n  there` → `hello there`). Represented as a bare string in the parse tree.

---

## 5. Containment Rules

### 5.1 Element Containers

| Container | Direct children |
|-----------|----------------|
| Document root | Zeroth section, headings |
| Heading | Section (optional), sub-headings |
| Zeroth section | Special keywords, comments, property drawer (opt.), any element |
| Normal section | Any element (no planning / property drawer at top level) |
| Greater Block | Any greater or lesser element (not same type) |
| Drawer | Any greater or lesser element (no nested drawer) |
| Dynamic Block | Any greater or lesser element (no nested dynamic block) |
| Footnote Definition | Any element |
| Item | Any element |
| Plain List | Items only |
| Property Drawer | Node properties only |
| Org Table | Table rows only |

### 5.2 Object-Bearing Elements

| Element / field | Permitted objects |
|-----------------|-------------------|
| Paragraph | All supported objects |
| Verse block | All supported objects |
| Table cell | Minimal-set objects + citations, export snippets, footnote refs, links, radio targets, targets, timestamps |
| Table row | Table cells only |
| Heading `TITLE` | Supported objects (no line breaks) |
| Item `TAG` | Supported objects |
| `#+CAPTION:` `VALUE` | Supported objects (no footnote refs) |
| Planning `TIMESTAMP` | Timestamps only |
| Clock | Inactive timestamps only |

### 5.3 Object Containers

| Object | May contain |
|--------|-------------|
| Bold / italic / underline / strike-through | Supported objects |
| Verbatim / code | Plain string only |
| Regular link `DESCRIPTION` | Minimal-set objects + export snippets, inline source blocks; plus plain/angle links |
| Radio link | Minimal-set objects |
| Radio target | Minimal-set objects |
| Footnote reference `DEFINITION` | Supported objects |
| Citation `GLOBALPREFIX` / `GLOBALSUFFIX` | Supported objects |
| Citation reference `KEYPREFIX` / `KEYSUFFIX` | Minimal-set objects |
| Table cell | Minimal-set objects + citations, export snippets, footnote refs, links, radio targets, targets, timestamps |

---

## 6. Configurable Behaviour

| Variable | Default | Role in this parser |
|----------|---------|---------------------|
| `org-todo-keywords-1` | `["TODO", "DONE"]` | Valid TODO keywords in heading `KEYWORD`. Updated by `#+TODO:` / `#+SEQ_TODO:` / `#+TYP_TODO:` special keywords during parse. **Must be configurable at parse time.** |
| `org-footnote-section` | `"Footnotes"` | Heading title treated as a footnote section. Case-significant. |
| `org-link-parameters` | `shell news mailto https http ftp help file elisp` | Recognised link type prefixes. |
| `org-element-parsed-keywords` | `["CAPTION"]` | Only `CAPTION` — its value is parsed as objects. |
| `org-element-affiliated-keywords` | `["CAPTION"]` | Only `CAPTION` is treated as an affiliated keyword in this subset. |

---

## 7. Parser Notes

### 7.1 Heading vs list item

`*` at column 0 followed by whitespace is always a heading. It cannot be a list item regardless of indentation context.

### 7.2 Footnote definition vs footnote reference

`[fn:LABEL]` on an **unindented** line is a footnote **definition** (greater element). The same pattern anywhere else is a footnote **reference** (object).

### 7.3 Underline markup takes priority over subscript

Since subscript is excluded from this subset, this conflict cannot arise — but underline markup (`_text_`) is the only form parsed when `_` appears between PRE/POST characters.

### 7.4 Affiliated keyword vs plain `#+CAPTION:`

`#+CAPTION:` immediately above an affiliatable element (no blank line) is an affiliated keyword — a property of that element, not a standalone node. A blank line between `#+CAPTION:` and the element causes it to be ignored.

### 7.5 Special keywords are zeroth-section only

`#+TITLE:` and other special keywords are only recognised in the zeroth section. The same `#+KEY: VALUE` pattern inside a heading section is unrecognised and discarded (not parsed as a keyword or any other element).

### 7.6 TODO keywords must be updated during parse

When `#+TODO:`, `#+SEQ_TODO:`, or `#+TYP_TODO:` special keywords are encountered in the zeroth section, `org-todo-keywords-1` must be updated **before** any subsequent heading is parsed. Heading `KEYWORD` fields depend on this list.

### 7.7 Comma-quoting in blocks

Lines inside block contents beginning with `,*` or `,#+` are unquoted by stripping the leading `,`. This allows org-like content to be embedded without triggering context-free heading recognition.

### 7.8 Blank line scoping in lists and footnote definitions

Two consecutive blank lines terminate a list item or footnote definition. Those blank lines are owned by the item/definition, not by any inner element.

### 7.9 Property drawer placement

A `:PROPERTIES:` drawer is only valid directly after a heading line or its planning line (no blank lines between), or in the zeroth section. Any such drawer elsewhere is an ordinary drawer.
