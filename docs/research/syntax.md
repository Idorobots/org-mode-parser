# Org Mode Syntax Reference

> Based on the official [Org Syntax v2](https://orgmode.org/worg/org-syntax.html) specification,
> as implemented by `org-element.el` in the Emacs Org Mode distribution.
> This document is a semi-formal reference for parser implementors.

---

## Table of Contents

1. [Foundational Concepts](#1-foundational-concepts)
2. [Document Structure](#2-document-structure)
3. [Elements](#3-elements)
   - 3.1 [Headings](#31-headings)
   - 3.2 [Sections](#32-sections)
   - 3.3 [Greater Elements](#33-greater-elements)
   - 3.4 [Lesser Elements](#34-lesser-elements)
4. [Objects](#4-objects)
5. [Containment Rules](#5-containment-rules)
6. [Affiliated Keywords](#6-affiliated-keywords)
7. [Configurable Behaviour](#7-configurable-behaviour)
8. [Disambiguation & Parser Notes](#8-disambiguation--parser-notes)

---

## 1. Foundational Concepts

### 1.1 Elements vs Objects

Every syntactic component belongs to one of two classes:

- **Elements** — exist at the same scope as, or a broader scope than, a paragraph. They cannot be contained within a paragraph.
- **Objects** — exist within a narrower scope than a paragraph; they are the inline constituents of element content.

Elements are further stratified (broadest → narrowest):

```
Headings  >  Sections  >  Greater Elements  >  Lesser Elements
```

**Lesser elements** cannot contain any other element. **Greater elements** can contain both greater and lesser elements. Sections contain any elements. Headings contain a section and sub-headings.

### 1.2 Blank Lines

A *blank line* is a line containing only `\t`, `\n`, `\r`, or space characters.

- Blank lines belong to the **preceding element** with the **narrowest possible scope**.
- Exception: blank lines at the end of **list items** and **footnote definitions** are not absorbed into inner elements, because those constructs use blank line counts as part of their own termination rules.

```
* Heading
Paragraph text.

```
The trailing blank line belongs to the paragraph (not the heading or section).

### 1.3 Indentation

- Indentation is a series of spaces and tabs at the start of a line.
- Most elements **can** be indented; exceptions are: headings, inlinetasks, footnote definitions, and diary sexps (all must start at column 0).
- Indentation is semantically meaningful **only in plain lists**, where tabs count as 8 spaces.
- The **common indentation** shared by all lines of an element is stripped by the parser.

### 1.4 Object Sets

Two frequently-referenced named sets:

| Set | Members |
|-----|---------|
| **Minimal set** | Plain text, text markup, entities, LaTeX fragments, superscripts, subscripts |
| **Standard set** | All objects *except* citation references and table cells |

### 1.5 Context-Free vs Context-Sensitive Elements

Only four element types are **context-free** (recognisable without surrounding context):

- Headings
- Sections
- Property drawers
- Planning lines

Every other syntactic component is context-sensitive — it only exists within specific environments (parent element types). This is a core constraint for any parser.

### 1.6 Syntax Pattern Notation

Patterns in this document use the same convention as the spec:

- **`TOKEN`** — uppercase names are semantic placeholders; `WORD`, `VALUE`, etc.
- **`literal`** — lowercase text and punctuation are matched verbatim.
- **`TOKEN (optional)`** — the component may be absent.
- **`PRE` / `POST`** — characters that must precede or follow an object but are not part of it; matched only against the containing object's content, not the surrounding document.
- A space between tokens means one or more horizontal whitespace characters (unless stated otherwise).

---

## 2. Document Structure

An Org document is a recursive tree rooted at an implicit `org-data` node.

```
org-data
├── zeroth-section (optional)   ← everything before the first heading
│   ├── comment* (optional)
│   ├── property-drawer (optional)
│   └── element*
└── heading*
    ├── section (optional)
    │   └── element*
    └── heading* (sub-headings, recursively)
```

**Key structural rules:**

- The **zeroth section** contains all content before the first heading. It may hold a property drawer (preceded optionally by comments), but **cannot** contain planning lines.
- A **heading** optionally owns a section, followed by zero or more sub-headings.
- A **section** contains one or more non-heading elements. Blank lines immediately following a heading's stars line are *not* part of the section — a heading with only blank lines has no section.
- Sub-headings terminate the parent section.

### Document-level example

```org
#+TITLE: Example

Zeroth section paragraph.

* Heading 1
  Section text.
** Sub-heading 1.1
** Sub-heading 1.2
   More section text.
* Heading 2
```

```
(org-data
  (section                     ; zeroth section
    (keyword "TITLE" "Example")
    (paragraph ...))
  (heading "Heading 1"
    (section (paragraph ...))
    (heading "Sub-heading 1.1")
    (heading "Sub-heading 1.2"
      (section (paragraph ...))))
  (heading "Heading 2"))
```

---

## 3. Elements

General form of an element:

```
BEGIN
CONTENTS          ← parsed child elements/objects
END
BLANK             ← trailing blank lines (belong to this element)
```

or, for verbatim elements:

```
BEGIN
VALUE             ← raw string, not parsed
END
BLANK
```

---

### 3.1 Headings

A heading is an **unindented** line:

```
STARS KEYWORD PRIORITY COMMENT TITLE TAGS
```

| Field | Description |
|-------|-------------|
| `STARS` | One or more `*` characters followed by a space. The count gives the nesting level. With `org-inlinetask` loaded, at most `org-inlinetask-min-level − 1` asterisks (default: 14). |
| `KEYWORD` (optional) | A member of `org-todo-keywords-1`. Case-significant. Called the *todo keyword*. |
| `PRIORITY` (optional) | `[#X]` where `X` is A–Z or an integer 0–64. Called the *priority cookie*. |
| `COMMENT` (optional) | The literal string `COMMENT`. Case-significant. Marks the heading as commented. |
| `TITLE` (optional) | Standard-set objects (excluding line breaks), matched after `KEYWORD` and `PRIORITY`. |
| `TAGS` (optional) | `:tag1:tag2:` — colon-delimited strings; each tag contains `[a-zA-Z0-9_@#%]`. |

**Special heading semantics:**

- Heading has `COMMENT` → the heading is *commented*.
- `TITLE` equals `org-footnote-section` (default: `"Footnotes"`) → it is a *footnote section*. Case-significant.
- `ARCHIVE` is among the tags → the heading is *archived*. Case-significant.
- A heading with `org-inlinetask-min-level` or more asterisks is an **inlinetask**, not a regular heading (when the `org-inlinetask` library is loaded).

**Examples:**

```org
*
** DONE
*** Some e-mail
**** TODO [#A] COMMENT Title :tag:a2%:
```

---

### 3.2 Sections

A section contains one or more non-heading elements. Sections only appear:

1. As the **zeroth section** — all content before the first heading.
2. Inside a **heading** — all content between the heading line and the next heading at the same or higher level (or end of document).

The zeroth section may contain a property drawer (optionally preceded by comments), but **cannot** contain a planning line. A normal section cannot contain planning or property drawers at the top level (those belong to the heading they follow).

---

### 3.3 Greater Elements

Greater elements can contain greater elements, lesser elements, or both — subject to the restrictions listed below.

**Universal restrictions on greater element contents:**

- May not contain elements of their own type (no nesting of the same greater element kind).
- Planning may only occur in a heading.
- Property drawers may only occur in a heading or the zeroth section.
- Node properties may only occur in property drawers.
- Items may only occur in plain lists.
- Table rows may only occur in tables.

---

#### 3.3.1 Greater Blocks

```
#+begin_NAME PARAMETERS
CONTENTS
#+end_NAME
```

| Field | Description |
|-------|-------------|
| `NAME` | Any non-whitespace string that is **not** a lesser block name (`comment`, `example`, `export`, `src`, `verse`). |
| `PARAMETERS` (optional) | Any characters except newline. |
| `CONTENTS` | Zero or more elements. No line may begin with `#+end_NAME`. |

Subtypes by `NAME`:

| NAME | Subtype |
|------|---------|
| `center` | center block |
| `quote` | quote block |
| anything else | special block |

---

#### 3.3.2 Drawers

```
:NAME:
CONTENTS
:end:
```

| Field | Description |
|-------|-------------|
| `NAME` | Word-constituent characters, hyphens, and underscores (`[A-Za-z0-9_-]`). |
| `CONTENTS` | Zero or more elements, except another drawer. |

`:end:` is case-insensitive.

---

#### 3.3.3 Dynamic Blocks

```
#+begin: NAME PARAMETERS
CONTENTS
#+end:
```

| Field | Description |
|-------|-------------|
| `NAME` | Any non-whitespace characters. |
| `PARAMETERS` (optional) | Any characters except newline. |
| `CONTENTS` | Zero or more elements, except another dynamic block. |

---

#### 3.3.4 Footnote Definitions

Must start at an **unindented** line:

```
[fn:LABEL] CONTENTS
```

| Field | Description |
|-------|-------------|
| `LABEL` | One or more digits, **or** a word string `[A-Za-z0-9_-]+`. |
| `CONTENTS` (optional) | Zero or more elements. Ends at: next footnote definition, next heading, two consecutive blank lines, or end of buffer. |

**Examples:**

```org
[fn:1] A short footnote.

[fn:long-note] This is a longer footnote.

It even contains a single blank line.
```

---

#### 3.3.5 Inlinetasks

Syntactically identical to headings, but with a level of at least `org-inlinetask-min-level` (default: 15) asterisks. Only recognised when the `org-inlinetask` library is loaded.

Inlinetasks can optionally be closed by a second headline at the same level carrying only the title `END`, allowing them to contain elements:

```org
*************** TODO some task
                DEADLINE: <2009-03-30 Mon>
                :PROPERTIES:
                  :SOMETHING: value
                :END:
                Body text.
*************** END
```

---

#### 3.3.6 Items

Items may only appear inside plain lists.

```
BULLET COUNTER-SET CHECK-BOX TAG CONTENTS
```

| Field | Description |
|-------|-------------|
| `BULLET` | `*`, `-`, or `+`; or `COUNTER.` / `COUNTER)` where `COUNTER` is digits or a single letter. Followed by whitespace or end of line. Note: `*` at column 0 followed by whitespace is always a heading, not an item. |
| `COUNTER-SET` (optional) | `[@COUNTER]` — resets the ordered list counter. |
| `CHECK-BOX` (optional) | `[ ]` (unchecked), `[X]` (checked), `[-]` (partial). |
| `TAG` (optional) | `TAG-TEXT ::` — text up to the last ` :: ` on the line; parsed with the standard object set. |
| `CONTENTS` (optional) | Zero or more elements. Ends at: next item, first line with indentation ≤ starting line (outside nested elements), or two consecutive blank lines. |

**Examples:**

```org
- item
3. [@3] set to three
+ [-] tag :: item contents
 * item (note leading space — valid item)
* not an item — this is a heading
```

---

#### 3.3.7 Plain Lists

A plain list is a set of **consecutive items at the same indentation level**. Items can themselves contain plain lists, producing nested lists.

The type of a plain list is determined by its **first item's bullet**:

| Condition | List type |
|-----------|-----------|
| First bullet has a `COUNTER` | ordered list |
| First item has a `TAG` | descriptive list |
| Otherwise | unordered list |

---

#### 3.3.8 Property Drawers

A special drawer that attaches properties to a heading, inlinetask, or (in the zeroth section) to the document.

Position rules:
- Directly after a heading line (no blank lines in between), or
- After a heading's planning line, or
- In the zeroth section (after optional blank lines and comments).

```
:properties:
CONTENTS
:end:
```

`CONTENTS` is zero or more **node properties** (no blank lines between them).

**Example:**

```org
* Heading
:PROPERTIES:
:CUSTOM_ID: someid
:END:
```

---

#### 3.3.9 Tables

A table begins with a line starting with `|` (Org type) or `+-` (table.el type).

**Org-type table:**

- Contains table rows.
- Ends at the first line not starting with `|`.
- May be followed by `#+TBLFM: FORMULAS` lines (formula annotations).

**Table.el-type table:**

- Ends at the first line not starting with `|` or `+`.
- Is parsed as a raw block; does not contain structured table rows.

**Example:**

```org
| Name  | Phone | Age |
|-------+-------+-----|
| Peter |  1234 |  24 |
| Anna  |  4321 |  25 |
#+TBLFM: @<$3..@>>$3 = $2 - 1
```

---

### 3.4 Lesser Elements

Lesser elements cannot contain any other element. Of all lesser elements, only **keywords** (when `KEY` is in `org-element-parsed-keywords`), **verse blocks**, **paragraphs**, and **table rows** can contain objects.

---

#### 3.4.1 Blocks (Lesser)

```
#+begin_NAME DATA
CONTENTS
#+end_NAME
```

`NAME` must be one of the five recognised lesser block names (case-insensitive):

| NAME | Subtype | CONTENTS |
|------|---------|----------|
| `comment` | comment block | Raw string (not parsed) |
| `example` | example block | Raw string (not parsed) |
| `export` | export block | Raw string (not parsed); `DATA` is mandatory and must be a single word (the backend) |
| `src` | source block | Raw string (not parsed); see below for `DATA` format |
| `verse` | verse block | Parsed as standard-set objects |

**Source block `DATA` format:**

```
LANGUAGE SWITCHES ARGUMENTS
```

- `LANGUAGE` — any non-whitespace characters.
- `SWITCHES` (optional) — space-separated `SWITCH` tokens. Each switch is one of: `-l "FORMAT"`, `+n NUMBER`, `-n NUMBER`, `-r`, `-i`, `-k`.
- `ARGUMENTS` (optional) — any characters except newline.

**Comma-quoting in block CONTENTS:**

Lines in block contents starting with `*` must be quoted with a leading comma (`,*`). Lines starting with `#+` may optionally be quoted (`,#+`). The parser strips all leading commas from `,*` and `,#+` lines.

---

#### 3.4.2 Clock

```
clock: INACTIVE-TIMESTAMP
clock: INACTIVE-TIMESTAMP-RANGE DURATION
clock: DURATION
```

`clock:` keyword is case-insensitive.

| Field | Description |
|-------|-------------|
| `INACTIVE-TIMESTAMP` | An inactive timestamp object. |
| `INACTIVE-TIMESTAMP-RANGE` | An inactive range timestamp object. |
| `DURATION` | `=> HH:MM` — `HH` is any number of digits; `MM` is exactly two digits. |

**Examples:**

```org
CLOCK: [2019-03-25 Mon 10:49]
CLOCK: [2019-03-25 Mon 10:49]--[2019-03-25 Mon 11:31] =>  0:42
```

---

#### 3.4.3 Diary Sexp

Must start at an **unindented** line:

```
%%SEXP
```

`SEXP` starts with `(` and has balanced parentheses.

```org
%%(org-calendar-holiday)
```

---

#### 3.4.4 Planning

```
HEADING
PLANNING
```

`PLANNING` is a line immediately following `HEADING` (no blank lines in between), containing one or more `KEYWORD: TIMESTAMP` pairs:

| `KEYWORD` | Meaning |
|-----------|---------|
| `DEADLINE` | Deadline timestamp |
| `SCHEDULED` | Scheduled timestamp |
| `CLOSED` | Closed timestamp |

If a keyword is repeated, the last instance wins.

**Example:**

```org
*** TODO watch "The Matrix"
    SCHEDULED: <1999-03-31 Wed>
*** TODO take over the world
    SCHEDULED: <2006-03-12 Sun> DEADLINE: <2034-03-22 Wed>
```

---

#### 3.4.5 Comments

One or more consecutive *comment lines*. A comment line starts with `#` followed by a space or end of line.

```org
# Just a comment
#
# Over multiple lines
```

---

#### 3.4.6 Fixed-Width Areas

One or more consecutive *fixed-width lines*. A fixed-width line starts with `:` followed by a space or end of line.

```org
: This is a
: fixed-width area
```

---

#### 3.4.7 Horizontal Rules

A line of at least five consecutive hyphens:

```
-----
```

---

#### 3.4.8 Keywords

```
#+KEY: VALUE
```

| Field | Description |
|-------|-------------|
| `KEY` | Any non-whitespace characters, except `call` (which forms a Babel Call). |
| `VALUE` | Any characters except newline. When `KEY` ∈ `org-element-parsed-keywords`, VALUE is parsed as standard-set objects (excluding footnote references). |

**Babel Call** (keyword subtype):

```
#+call: NAME(ARGUMENTS)
#+call: NAME[HEADER1](ARGUMENTS)
#+call: NAME(ARGUMENTS)[HEADER2]
#+call: NAME[HEADER1](ARGUMENTS)[HEADER2]
```

`NAME` — non-newline characters excluding `[]()`.
`ARGUMENTS`, `HEADER1`, `HEADER2` — non-newline characters; brackets/parens balanced within each field.

See [§6 Affiliated Keywords](#6-affiliated-keywords) for how keywords immediately preceding elements are treated differently.

---

#### 3.4.9 LaTeX Environments

```
\begin{NAME}EXTRA
CONTENTS
\end{NAME}
```

| Field | Description |
|-------|-------------|
| `NAME` | Non-empty string of `[A-Za-z0-9*]`. |
| `EXTRA` (optional) | Any characters not containing `\end{NAME}`. |
| `CONTENTS` (optional) | Any characters not containing `\end{NAME}`. |

**Example:**

```org
\begin{align*}
2x - 5y &= 8 \\
3x + 9y &= -12
\end{align*}
```

---

#### 3.4.10 Node Properties

Node properties can only appear inside **property drawers**.

```
:NAME: VALUE
:NAME:
:NAME+: VALUE
:NAME+:
```

| Field | Description |
|-------|-------------|
| `NAME` | Non-empty string of non-whitespace characters, not ending with `+`. |
| `VALUE` (optional) | Any characters except newline. |

The `+` suffix form **appends** to an existing property value rather than replacing it.

---

#### 3.4.11 Paragraphs

Paragraphs are the **default element** — any content not recognised as another element type is a paragraph. They are terminated by blank lines or other element boundaries.

Paragraphs can contain the **standard set** of objects.

---

#### 3.4.12 Table Rows

A table row starts with `|` followed by either:

- Zero or more table cells → a *standard* row.
- A hyphen `-` (any non-newline characters may follow) → a *rule* row (separator).

Table rows can only appear in Org-type tables.

---

## 4. Objects

Objects are inline components found within element content. They can only appear in:

- Heading `TITLE` fields
- Inlinetask `TITLE` fields
- Item `TAG` fields
- Keyword / affiliated keyword `VALUE` fields (when `KEY` ∈ `org-element-parsed-keywords`)
- Clock `INACTIVE-TIMESTAMP` and `INACTIVE-TIMESTAMP-RANGE` (timestamps only)
- Planning `TIMESTAMP` fields (timestamps only)
- Paragraphs
- Table cells
- Table rows (table cells only)
- Verse blocks

Objects have the same general structure as elements but trailing spaces replace blank lines:

```
BEGIN CONTENTS END TRAILING-SPACES
```

Most objects cannot themselves contain objects; those that can are noted explicitly.

Trailing spaces after an object are part of that object.

---

### 4.1 Entities

```
\NAME POST
\NAME{}
\_SPACES
```

- `NAME` — a string with a valid entry in `org-entities` or `org-entities-user`.
- `POST` (not separated from `NAME` by whitespace) — end of line, or a non-alphabetic character.
- `\_SPACES` — one or more spaces forming a whitespace entity.

`\NAME{}` forces recognition even when the following character would otherwise be ambiguous.

**Examples:**

```org
1\cent.
\alpha{}
\_ 
```

See [Appendix A](#appendix-a-partial-entity-list) for a partial entity list.

---

### 4.2 LaTeX Fragments

Three forms:

**Command form:**

```
\NAME BRACKETS
```

`NAME` — `[A-Za-z]+\*?` with **no** entry in `org-entities` / `org-entities-user`.
`BRACKETS` (optional, no whitespace before) — `[CONTENTS1]` or `{CONTENTS2}` where `CONTENTS1` excludes `{}[]` and newline; `CONTENTS2` excludes `{}` and newline.

**Inline math delimiters:**

```
\(CONTENTS\)
\[CONTENTS\]
```

`CONTENTS` — any characters not containing the closing delimiter.

**TeX-style dollar math:**

```
$$CONTENTS$$
PRE$CHAR$POST
PRE$BORDER1 BODY BORDER2$POST
```

| Token | Description |
|-------|-------------|
| `PRE` | Beginning of line or character other than `$`. |
| `CHAR` | Non-whitespace, not `.`, `,`, `?`, `;`, `"`. |
| `POST` | Punctuation, space, or end of line. |
| `BORDER1` | Non-whitespace, not `.`, `,`, `;`, `$`. |
| `BODY` | Any characters except `$`. |
| `BORDER2` | Non-whitespace, not `.`, `,`, `$`. |

**Examples:**

```org
\alpha
\enlargethispage{2\baselineskip}
\(e^{i \pi}\)
\[E = mc^2\]
$$1+1=2$$
$x^2$
```

---

### 4.3 Export Snippets

```
@@BACKEND:VALUE@@
```

| Field | Description |
|-------|-------------|
| `BACKEND` | `[A-Za-z0-9-]+` |
| `VALUE` (optional) | Any characters not containing `@@`. |

**Example:**

```org
@@html:<b>@@bold@@html:</b>@@
```

---

### 4.4 Footnote References

Three forms:

```
[fn:LABEL]
[fn:LABEL:DEFINITION]
[fn::DEFINITION]
```

| Field | Description |
|-------|-------------|
| `LABEL` | `[A-Za-z0-9_-]+` |
| `DEFINITION` (optional) | Standard-set objects; square brackets must be balanced within. |

- Second form → *inline footnote* (label + definition together).
- Third form → *anonymous footnote* (no label).
- First form on an **unindented** line is a **footnote definition** (element), not a reference.

---

### 4.5 Citations

```
[cite CITESTYLE: REFERENCES]
[cite CITESTYLE: GLOBALPREFIX;REFERENCES]
[cite CITESTYLE: REFERENCES;GLOBALSUFFIX]
[cite CITESTYLE: GLOBALPREFIX;REFERENCES;GLOBALSUFFIX]
```

`cite` and `CITESTYLE` are not separated by whitespace.

| Field | Description |
|-------|-------------|
| `CITESTYLE` (optional) | `/STYLE` or `/STYLE/VARIANT`; `STYLE` is `[A-Za-z0-9_-]+`; `VARIANT` is `[A-Za-z0-9_\-/]+`. |
| `GLOBALPREFIX` (optional) | Standard-set objects; balanced brackets; no `;` and no `@KEY` subsequences. |
| `REFERENCES` | One or more citation reference objects separated by `;`. |
| `GLOBALSUFFIX` (optional) | Same constraints as `GLOBALPREFIX`. |

**Examples:**

```org
[cite:@key]
[cite/t: see;@source1;@source2;by Smith /et al./]
```

---

### 4.6 Citation References

Citation references only appear inside **citations**.

```
KEYPREFIX @KEY KEYSUFFIX
```

No whitespace between `KEYPREFIX`, `@KEY`, and `KEYSUFFIX`.

| Field | Description |
|-------|-------------|
| `KEYPREFIX` (optional) | Minimal-set objects; balanced brackets; no `;` or `@KEY` subsequences. |
| `KEY` | `[A-Za-z0-9\-.:?!` ` '/*@+|(){}><&_^$#%~]+` |
| `KEYSUFFIX` (optional) | Minimal-set objects; balanced brackets; no `;`. |

---

### 4.7 Inline Babel Calls

```
call_NAME(ARGUMENTS)
call_NAME[HEADER1](ARGUMENTS)
call_NAME(ARGUMENTS)[HEADER2]
call_NAME[HEADER1](ARGUMENTS)[HEADER2]
```

| Field | Description |
|-------|-------------|
| `NAME` | Non-whitespace, excluding `[]()`. |
| `ARGUMENTS`, `HEADER1`, `HEADER2` | Non-newline characters; respective brackets balanced. |

---

### 4.8 Inline Source Blocks

```
src_LANG{BODY}
src_LANG[HEADERS]{BODY}
```

| Field | Description |
|-------|-------------|
| `LANG` | Characters excluding whitespace, `[`, and `{`. |
| `HEADERS` (optional) | Non-newline characters; balanced `[]`. |
| `BODY` | Non-newline characters; balanced `{}`. |

**Example:**

```org
src_python[:exports both]{print("hello")}
```

---

### 4.9 Line Breaks

Must appear at the end of an otherwise non-blank line:

```
PRE\\SPACE
```

- `PRE` — anything except a backslash.
- `SPACE` — zero or more space/tab characters.

This forces a hard line break in the rendered output.

---

### 4.10 Links

Links come in four subtypes.

#### 4.10.1 Radio Links

```
PRE RADIO POST
```

- `PRE` — non-alphanumeric or line-breakable character.
- `RADIO` — one or more objects matching a radio target; contains the minimal object set.
- `POST` — non-alphanumeric or line-breakable character.

Radio links are **auto-generated** — when a radio target `<<<text>>>` is defined, every occurrence of the matching text elsewhere in the document becomes a radio link automatically.

#### 4.10.2 Plain Links

```
PRE LINKTYPE:PATHPLAIN POST
```

- `PRE` — non-word-constituent character.
- `LINKTYPE` — a registered link type (member of `org-link-parameters`).
- `PATHPLAIN` — non-whitespace, non-bracket characters; may contain paren-wrapped substrings up to depth 2; must end with a non-punctuation non-whitespace character, `/`, or a paren-wrapped substring.
- `POST` — non-word-constituent character.

Regexp for `PATHPLAIN`:
```
(?:[^ \t\n\[\]<>()]|\((?:[^ \t\n\[\]<>()]|\([^ \t\n\[\]<>()]*\))*\))+(?:[^[:punct:] \t\n]|\/|\((?:[^ \t\n\[\]<>()]|\([^ \t\n\[\]<>()]*\))*\))
```

**Example:** `https://orgmode.org`

#### 4.10.3 Angle Links

```
<LINKTYPE:PATHANGLE>
```

- `LINKTYPE` — registered link type.
- `PATHANGLE` — any characters except `>`; newlines and indentation are ignored.

Angle brackets allow a more permissive path syntax than plain links.

**Example:** `<https://orgmode.org/path with spaces>`

#### 4.10.4 Regular Links

```
[[PATHREG]]
[[PATHREG][DESCRIPTION]]
```

`PATHREG` path types:

| Pattern | Type |
|---------|------|
| `FILENAME` | `file` — absolute or relative path |
| `LINKTYPE:PATHINNER` | `LINKTYPE` |
| `LINKTYPE://PATHINNER` | `LINKTYPE` |
| `id:ID` | `id` |
| `#CUSTOM-ID` | `custom-id` |
| `(CODEREF)` | `coderef` |
| `FUZZY` | `fuzzy` — matches heading text, target, or radio target |

- `PATHINNER`, `ID`, `CUSTOM-ID`, `CODEREF`, `FUZZY` — any characters except `[` and `]`.
- Backslashes and square brackets inside `PATHREG` must be escaped (`\]`, `\\`).
- Spaces, tabs, and newlines inside `PATHREG` are collapsed to a single space.

`DESCRIPTION` (optional):
- Minimal-set objects plus export snippets, inline babel calls, inline source blocks, macros, and statistics cookies.
- May contain another link only if it is a plain or angle link.
- May contain `[` but not `]]`.

**Examples:**

```org
[[https://orgmode.org][The Org project homepage]]
[[file:orgmanual.org]]
[[My Target]]
[[#custom-id]]
[[(code-ref)]]
```

---

### 4.11 Macros

```
{{{NAME}}}
{{{NAME(ARGUMENTS)}}}
```

| Field | Description |
|-------|-------------|
| `NAME` | Starts with `[A-Za-z]`, followed by `[A-Za-z0-9_-]*`. |
| `ARGUMENTS` (optional) | Any characters not containing `}}}`. Values separated by `,`. Non-separating commas escaped with `\`. |

**Examples:**

```org
{{{title}}}
{{{two_arg_macro(1, 2)}}}
{{{two_arg_macro(1\,a, 2)}}}
```

---

### 4.12 Targets and Radio Targets

**Target:**

```
<<TARGET>>
```

`TARGET` — any characters except `<`, `>`, `\n`; cannot start or end with whitespace.

**Radio target:**

```
<<<CONTENTS>>>
```

`CONTENTS` — minimal-set objects; starts and ends with a non-whitespace character; excludes `<`, `>`, `\n`.

Radio targets create automatic links throughout the document wherever their content is matched (see [Radio Links](#4101-radio-links)).

---

### 4.13 Statistics Cookies

```
[PERCENT%]
[NUM1/NUM2]
```

Both `PERCENT`, `NUM1`, `NUM2` are optional non-negative integers (one or more digits). These indicate task completion progress.

**Examples:**

```org
[33%]
[1/3]
[%]
[/]
```

---

### 4.14 Subscript and Superscript

```
CHAR_SCRIPT     (subscript)
CHAR^SCRIPT     (superscript)
```

`CHAR` — any non-whitespace character.

`SCRIPT` is one of:

1. `*` — a single asterisk.
2. `{...}` or `(...)` — balanced braces or parens; may contain balanced sub-brackets and standard-set objects.
3. Inline script: `SIGN CHARS FINAL` (no whitespace between parts):
   - `SIGN` (optional) — `+`, `-`, or empty.
   - `CHARS` — zero or more `[A-Za-z0-9,\.]` characters.
   - `FINAL` — one alphanumeric character.

**Examples:**

```org
x^2
x^-2
A_i,j
y_(i^th)
x^{y^{z}}
pecularity^*
```

**Disambiguation:** underline markup (`_text_`) takes priority over subscript when they conflict.

---

### 4.15 Table Cells

```
CONTENTS SPACES|
CONTENTS SPACES END-OF-LINE
```

- `CONTENTS` — zero or more objects not containing `|`; may contain: minimal-set objects, citations, export snippets, footnote references, links, macros, radio targets, targets, timestamps.
- `SPACES` — zero or more spaces (for column alignment).
- The final `|` may be omitted in the last cell of a table row.

---

### 4.16 Timestamps

Timestamps come in several subtypes based on delimiter and structure.

#### Diary timestamps

```
<%%(SEXP)>
<%%(SEXP) TIME>
<%%(SEXP) TIME-TIME>
```

`SEXP` — any characters except `>` and `\n`.

#### Active and inactive timestamps

```
<DATE TIME REPEATER-OR-DELAY>          active
[DATE TIME REPEATER-OR-DELAY]          inactive
```

#### Range timestamps

```
<DATE TIME REPEATER-OR-DELAY>--<DATE TIME REPEATER-OR-DELAY>   active range (multi-day)
<DATE TIME-TIME REPEATER-OR-DELAY>                             active range (same-day)
[DATE TIME REPEATER-OR-DELAY]--[DATE TIME REPEATER-OR-DELAY]   inactive range (multi-day)
[DATE TIME-TIME REPEATER-OR-DELAY]                             inactive range (same-day)
```

**Field definitions:**

| Field | Pattern | Description |
|-------|---------|-------------|
| `DATE` | `YYYY-MM-DD DAYNAME` | `Y`,`M`,`D` are digits; `DAYNAME` is optional non-whitespace excluding `+`, `-`, `]`, `>`, digits, `\n`. |
| `TIME` (optional) | `H:MM` | `H` is 1–2 digits; `MM` is exactly 2 digits. |
| `REPEATER-OR-DELAY` (optional) | See below | Zero or one `REPEATER` and/or one `DELAY`, in any order. |

**Repeater:**

```
MARK VALUE UNIT
MARK VALUE UNIT/VALUE UNIT    (with upper bound)
```

`MARK` — `+` (cumulative), `++` (catch-up), `.+` (restart).
`VALUE` — one or more digits.
`UNIT` — `h` (hour), `d` (day), `w` (week), `m` (month), `y` (year).

**Delay:**

```
MARK VALUE UNIT
```

`MARK` — `-` (all type), `--` (first type).
`VALUE`, `UNIT` — as above.

No whitespace between `MARK`, `VALUE`, `UNIT`.

**Examples:**

```org
<1997-11-03 Mon 19:15>
[2004-08-24 Tue]
[2004-08-24 Tue]--[2004-08-26 Thu]
<2012-02-08 Wed 20:00 ++1d>
<2030-10-05 Sat +1m -3d>
<2012-03-29 Thu ++1y/2y>
<%%(diary-float t 4 2)>
<%%(diary-float t 4 2) 12:00-14:00>
```

---

### 4.17 Text Markup

Six markup types, all following the same pattern:

```
PRE MARKER CONTENTS MARKER POST
```

No whitespace between any of these tokens.

| Token | Description |
|-------|-------------|
| `PRE` | Whitespace, `-`, `(`, `{`, `'`, `"`, or beginning of line. |
| `MARKER` | One of: `*`, `/`, `_`, `=`, `~`, `+` (see table below). |
| `CONTENTS` | For `=` and `~`: a raw string. For others: standard-set objects. In both cases, must not start or end with whitespace. |
| `POST` | Whitespace, `-`, `.`, `,`, `;`, `:`, `!`, `?`, `'`, `)`, `}`, `[`, `"`, `\`, or end of line. |

Markup types:

| Marker | Type |
|--------|------|
| `*` | bold |
| `/` | italic |
| `_` | underline |
| `=` | verbatim (contents not parsed) |
| `~` | code (contents not parsed) |
| `+` | strike-through |

**Examples:**

```org
*bold*  /italic/  _underline_  =verbatim=  ~code~  +strike+
Org is a /plaintext markup syntax/ developed with *Emacs* in 2003.
```

---

### 4.18 Plain Text

Any string that does not match any other object type is plain text. Within plain text, all whitespace is collapsed to a single space (e.g., `hello\n  there` → `hello there`).

In `org-element.el`, plain text objects are represented as bare strings for performance.

---

## 5. Containment Rules

The table below summarises which constructs may appear as direct children of each container. "Elements" means any greater or lesser element. "Objects (std)" means standard-set objects. "Objects (min)" means minimal-set objects.

### 5.1 Element Containers

| Container | May directly contain |
|-----------|---------------------|
| `org-data` (document root) | Zeroth section, headings |
| Heading | Section, sub-headings |
| Section (zeroth) | Comments (optional), property drawer (optional), elements |
| Section (normal) | Elements (no planning, no property drawer at top level) |
| Greater Block | Greater elements, lesser elements (not elements of own type) |
| Drawer | Greater elements, lesser elements (not another drawer) |
| Dynamic Block | Greater elements, lesser elements (not another dynamic block) |
| Footnote Definition | Elements (ends at next footnote def / heading / 2 blank lines) |
| Inlinetask | Elements (only if `END` form used) |
| Item | Elements |
| Plain List | Items only |
| Property Drawer | Node properties only (no blank lines between) |
| Table (Org type) | Table rows |

### 5.2 Object-Bearing Elements

| Element | May contain |
|---------|-------------|
| Paragraph | Standard-set objects |
| Verse Block | Standard-set objects |
| Table Cell | Minimal-set objects + citations, export snippets, footnote refs, links, macros, radio targets, targets, timestamps |
| Table Row | Table cells only |
| Heading TITLE | Standard-set objects (no line breaks) |
| Inlinetask TITLE | Standard-set objects (no line breaks) |
| Item TAG | Standard-set objects |
| Keyword VALUE | Standard-set objects (when KEY ∈ `org-element-parsed-keywords`) |
| Planning | Timestamps only |
| Clock | Inactive timestamps only |

### 5.3 Object Containers

| Object | May contain |
|--------|-------------|
| Bold / Italic / Underline / Strike-through | Standard-set objects |
| Verbatim / Code | Plain string only (not parsed) |
| Regular Link DESCRIPTION | Minimal-set objects + export snippets, inline babel calls, inline source blocks, macros, statistics cookies; plus plain/angle links |
| Radio Link RADIO | Minimal-set objects |
| Radio Target CONTENTS | Minimal-set objects |
| Footnote Reference DEFINITION | Standard-set objects |
| Citation | Citation reference objects; GLOBALPREFIX/GLOBALSUFFIX: standard-set objects |
| Citation Reference | KEYPREFIX/KEYSUFFIX: minimal-set objects |
| Subscript / Superscript SCRIPT | Standard-set objects (when `{}`/`()` form) |
| Table Cell CONTENTS | Minimal-set + citations, export snippets, footnote refs, links, macros, radio targets, targets, timestamps |

---

## 6. Affiliated Keywords

With the exception of: comments, clocks, headings, inlinetasks, items, node properties, planning, property drawers, sections, and table rows — every element type may be assigned metadata via *affiliated keywords* placed **immediately above** the element (no blank lines between the keyword and element).

Affiliated keywords are **not** independent elements; they are properties of the element they precede.

Three patterns:

```
#+KEY: VALUE
#+KEY[OPTVAL]: VALUE
#+attr_BACKEND: VALUE
```

| Field | Description |
|-------|-------------|
| `KEY` | Member of `org-element-affiliated-keywords` (default: `CAPTION`, `DATA`, `HEADER`, `NAME`, `PLOT`, `RESULTS`). |
| `BACKEND` | `[A-Za-z0-9_-]+` |
| `OPTVAL` (optional) | Any characters except newline; balanced brackets. Only valid when `KEY` ∈ `org-element-dual-keywords`. |
| `VALUE` | Any characters except newline; parsed as standard-set objects (no footnote refs) when `KEY` ∈ `org-element-parsed-keywords`. |

**Value accumulation rules:**

- Repeating an affiliated keyword overwrites the prior value.
- Exception: `#+attr_BACKEND:` lines are **accumulated** (concatenated).
- `#+caption:` and `#+results:` (dual keywords) — multiple instances are concatenated, with `OPTVAL` forming a secondary list.

**Example:**

```org
#+name: fig-1
#+caption: Figure 1
#+caption[short]: Short caption
[[file:image.png]]
```

When no element follows the affiliated keyword pattern, it is parsed as an ordinary keyword instead.

---

## 7. Configurable Behaviour

Several aspects of Org syntax are governed by Emacs Lisp variables. Parsers targeting non-Emacs environments must either hard-code the defaults or provide equivalent configuration mechanisms.

| Variable | Default value | Effect |
|----------|---------------|--------|
| `org-todo-keywords-1` | `["TODO", "DONE"]` | Determines valid TODO keywords in heading KEYWORD field. **Must be configurable at parse time** — in-file `#+TODO:` keywords change this. |
| `org-inlinetask-min-level` | `15` | Minimum asterisk count that distinguishes inlinetasks from headings. |
| `org-footnote-section` | `"Footnotes"` | Heading title treated as a footnote section container. Case-significant. |
| `org-element-parsed-keywords` | `["CAPTION"]` | Keyword KEYs whose VALUEs are parsed as objects rather than raw strings. |
| `org-element-affiliated-keywords` | `["CAPTION", "DATA", "HEADER", "NAME", "PLOT", "RESULTS"]` | KEYs that are treated as affiliated keywords. |
| `org-element-dual-keywords` | `["CAPTION", "RESULTS"]` | Affiliated keywords that support `[OPTVAL]` and value concatenation. |
| `org-link-parameters` | `shell, news, mailto, https, http, ftp, help, file, elisp` | Recognised link type prefixes for plain, angle, and regular links. |
| `org-entities` / `org-entities-user` | (large built-in list) | Valid entity names for `\NAME` syntax. |

---

## 8. Disambiguation & Parser Notes

### 8.1 Priority rules

When two patterns are ambiguous, the following priorities apply:

1. **Heading `*` vs list item `*`**: A `*` at column 0 followed by whitespace is always a heading.
2. **Footnote definition vs footnote reference**: `[fn:LABEL]` on an **unindented** line is a footnote definition (element), not a reference (object).
3. **Underline markup vs subscript**: `(_text_)` — underline markup takes priority.
4. **Affiliated keyword vs ordinary keyword**: `#+KEY: VALUE` immediately above a valid affiliatable element → affiliated keyword; otherwise → ordinary keyword. A blank line between the two forces the keyword to be ordinary.
5. **Greater block vs lesser block**: the `NAME` field determines which; lesser block names (`comment`, `example`, `export`, `src`, `verse`) form lesser blocks; all other names form greater blocks.

### 8.2 Context-free elements

Only headings, sections, property drawers, and planning lines can be identified purely by examining the beginning of a line. All other elements require context (knowledge of their parent container) to be recognised.

In `org-element.el`, this means `org-element-at-point` and `org-element-context` always traverse up to the parent heading and parse top-down.

### 8.3 TODO keyword configurability

TODO keywords **cannot** be hardcoded in a tokeniser. They are set on a per-document basis via in-file keywords (`#+TODO:`, `#+SEQ_TODO:`, `#+TYP_TODO:`) and must be loaded before the document is parsed. Without the correct keyword list, the `KEYWORD` field of headings will be silently misidentified.

### 8.4 Comma-quoting in blocks

Lines inside block CONTENTS that begin with `*` or `#+` may be escaped with a leading `,`. The parser strips the leading `,` from `,*` and `,#+` lines. This allows org files to embed org-like content without triggering context-free element recognition.

### 8.5 Whitespace in regular link paths

Sequences of spaces, tabs, and newlines inside `[[PATHREG]]` are normalised to a single space. This is intentional (RFC 3986 compliance is deliberately sacrificed for usability).

### 8.6 Blank line scoping in list items and footnote definitions

Blank lines **within** list items and footnote definitions are absorbed by the item or definition itself (not inner elements), because blank line count is part of their termination logic: two consecutive blank lines end a list item or footnote definition.

### 8.7 Property drawer placement

A property drawer is only valid:

- Directly after a heading line (with no blank lines), or
- After a heading's planning line (with no blank lines), or
- In the zeroth section (after optional blank lines and comments).

Any `:PROPERTIES:` drawer elsewhere is parsed as an ordinary drawer.

### 8.8 Indentation stripping

The common indentation prefix shared by all lines of an element is removed by the parser. This affects how content inside indented blocks/items is exposed to consumers.

---

## Appendix A: Partial Entity List

A selection of commonly used entities. The full list is in `org-entities.el`.

| Name | Character | Name | Character |
|------|-----------|------|-----------|
| `alpha` | α | `Alpha` | Α |
| `beta` | β | `Beta` | Β |
| `gamma` | γ | `Gamma` | Γ |
| `delta` | δ | `Delta` | Δ |
| `epsilon` | ε | `Epsilon` | Ε |
| `theta` | θ | `Theta` | Θ |
| `lambda` | λ | `Lambda` | Λ |
| `mu` | μ | `pi` | π |
| `sigma` | σ | `Sigma` | Σ |
| `omega` | ω | `Omega` | Ω |
| `infin` | ∞ | `empty` | ∅ |
| `nabla` | ∇ | `partial` | ∂ |
| `isin` | ∈ | `notin` | ∉ |
| `forall` | ∀ | `exist` | ∃ |
| `and` | ∧ | `or` | ∨ |
| `cap` | ∩ | `cup` | ∪ |
| `sub` | ⊂ | `sup` | ⊃ |
| `ne` | ≠ | `le` | ≤ |
| `ge` | ≥ | `equiv` | ≡ |
| `rarr` | → | `larr` | ← |
| `uarr` | ↑ | `darr` | ↓ |
| `harr` | ↔ | `rArr` | ⇒ |
| `lArr` | ⇐ | `hArr` | ⇔ |
| `nbsp` | (non-breaking space) | `shy` | (soft hyphen) |
| `copy` | © | `reg` | ® |
| `trade` | ™ | `deg` | ° |
| `pound` | £ | `euro` | € |
| `cent` | ¢ | `yen` | ¥ |
| `mdash` | — | `ndash` | – |
| `laquo` | « | `raquo` | » |
| `ldquo` | " | `rdquo` | " |
| `lsquo` | ' | `rsquo` | ' |
| `dagger` | † | `Dagger` | ‡ |
| `check` | ✓ | `star` | * |
| `clubs` | ♣ | `spades` | ♠ |
| `hearts` | ♥ | `diams` | ♦ |
