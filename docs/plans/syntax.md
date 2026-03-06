# Target Org Syntax — Formal Grammar

> PEG grammar for the target subset of Org Mode syntax defined in
> [`../research/target-syntax.md`](../research/target-syntax.md).
> Intended as the blueprint for a tree-sitter parser.

---

## Table of Contents

1. [Notation](#1-notation)
2. [Document Structure](#2-document-structure)
3. [Headings](#3-headings)
4. [Sections](#4-sections)
5. [Element Dispatch](#5-element-dispatch)
6. [Greater Elements](#6-greater-elements)
7. [Lesser Elements](#7-lesser-elements)
8. [Objects](#8-objects)
9. [Object Sets](#9-object-sets)
10. [Lexical Primitives](#10-lexical-primitives)
11. [Excluded Features](#11-excluded-features)
12. [External Scanner Requirements](#12-external-scanner-requirements)

---

## 1. Notation

### 1.1 PEG Operators

| Syntax | Meaning |
|--------|---------|
| `<-` | Rule definition |
| `e1 e2` | Sequence (match `e1` then `e2`) |
| `e1 / e2` | Ordered choice (try `e1`; if it fails, try `e2`) |
| `e*` | Zero or more repetitions (greedy) |
| `e+` | One or more repetitions (greedy) |
| `e?` | Optional (zero or one) |
| `&e` | Positive lookahead (match `e` without consuming) |
| `!e` | Negative lookahead (succeed only if `e` does not match) |
| `(...)` | Grouping |
| `'...'` | Case-sensitive literal string |
| `'...'i` | Case-insensitive literal string |
| `[...]` | Character class (same as regex `[...]`) |
| `.` | Any single character |

### 1.2 Conventions

| Convention | Meaning |
|------------|---------|
| `rule_name` | **Named node** — appears in the concrete syntax tree (CST). |
| `_rule_name` | **Hidden rule** — structural grouping; does not produce its own CST node. |
| `_UPPER_CASE` | **Lexical terminal** — a token-level pattern. |
| `field:rule` | **Field label** — names a child for tree-sitter `field()` access. |
| `# ...` | Comment. |
| `# @scanner: ...` | Requires the tree-sitter **external scanner**. |
| `# @semantic: ...` | Validated as a **post-processing** step, not in the grammar. |

### 1.3 Implicit Whitespace

Unlike some PEG frameworks, this grammar does **not** auto-skip whitespace.
Every space and newline is matched explicitly through `_S`, `_NL`, etc.

### 1.4 Tree-Sitter Mapping

| PEG | tree-sitter `grammar.js` |
|-----|--------------------------|
| `e1 e2` | `seq(e1, e2)` |
| `e1 / e2` | `choice(e1, e2)` |
| `e*` | `repeat(e)` |
| `e+` | `repeat1(e)` |
| `e?` | `optional(e)` |
| `'x'i` | Case-insensitive token via external scanner or regex |
| `field:rule` | `field('field', rule)` |
| `_rule` | Rule name prefixed with `_` (hidden) |

---

## 2. Document Structure

```peg
document <- zeroth_section? heading* _EOI
```

An Org document is a tree rooted at an implicit `document` node.
It contains an optional zeroth section (everything before the first heading)
followed by zero or more top-level headings.

---

## 3. Headings

```peg
heading <- stars:stars _S
           todo:todo_keyword?
           priority:priority?
           is_comment:_COMMENT_TOKEN?
           title:_heading_title?
           tags:tags?
           _NL
           planning:planning?
           properties:property_drawer?
           _blank_line*
           body:section?
           heading*

# @scanner: A heading at level N may only contain sub-headings at
# level > N. The external scanner tracks heading levels and emits
# an implicit close when a same-or-higher-level heading is reached.

stars         <- _BOL '*'+ &_S
# @scanner: Must begin at column 0.

todo_keyword  <- _TODO_KW _S
# @scanner: _TODO_KW matches any member of org-todo-keywords-1.
# Default set: 'TODO', 'DONE'.
# Updated by #+TODO: / #+SEQ_TODO: / #+TYP_TODO: during parse.

priority      <- '[#' ([A-Z] / [0-9]+) ']' _S
# X is A-Z (single letter) or an integer 0-64 (one or more digits).
# @semantic: Integer range 0-64 validated in post-processing.

_COMMENT_TOKEN <- 'COMMENT' _S

_heading_title <- _object_nolb+
# Heading title: supported objects excluding line breaks.
# Extends to the end of line minus any trailing tags.

tags          <- ':' tag (':' tag)* ':'
tag           <- [A-Za-z0-9_@#%]+
```

**Semantic flags** (derived, not grammatical):

- `is_comment` present -> heading is *commented*.
- `title` text equals `org-footnote-section` (default `"Footnotes"`) -> *footnote section*.
- `ARCHIVE` among `tags` -> heading is *archived*.

---

## 4. Sections

```peg
# Zeroth section: everything before the first heading.
# May hold special keywords, comments, a property drawer, and elements.
# Cannot hold planning.
zeroth_section <- (_zs_preamble / _blank_line)*
                  properties:property_drawer?
                  (_zs_element / _blank_line)*

_zs_preamble   <- special_keyword / comment

# Normal section: inside a heading, after optional planning/property-drawer/blank-lines.
section        <- (_section_element / _blank_line)+
```

The zeroth section's property drawer may only appear after blank lines and
comments (no other content before it). If any other element precedes
`:PROPERTIES:`, it is parsed as an ordinary drawer.

---

## 5. Element Dispatch

```peg
# --- Zeroth-section elements ---
_zs_element <- affiliated_keyword+ _affiliatable
             / special_keyword
             / _non_affiliatable
             / _affiliatable

# --- Normal section elements ---
_section_element <- affiliated_keyword+ _affiliatable
                  / special_keyword
                  / _non_affiliatable
                  / _affiliatable

# --- Affiliatable elements (may be preceded by affiliated keywords) ---
_affiliatable <- _greater_block
               / drawer
               / dynamic_block
               / footnote_definition
               / plain_list
               / org_table
               / tableel_table
               / _lesser_block
               / diary_sexp
               / fixed_width
               / horizontal_rule
               / paragraph                          # catch-all, must be last

# --- Non-affiliatable elements ---
_non_affiliatable <- comment
                   / clock
```

Ordered choice ensures that specific element patterns are tried before the
paragraph catch-all. `affiliated_keyword+ _affiliatable` is tried first: if
the keyword lines are not followed by an affiliatable element, they fall
through and are consumed as paragraph text.

---

## 6. Greater Elements

### 6.1 Greater Blocks

```peg
_greater_block <- center_block / quote_block / special_block

center_block <- _BOL _INDENT? '#+begin_center'i parameters:_block_params? _NL
                body:_gblock_body
                _BOL _INDENT? '#+end_center'i _TRAILING? _NL

quote_block  <- _BOL _INDENT? '#+begin_quote'i parameters:_block_params? _NL
                body:_gblock_body
                _BOL _INDENT? '#+end_quote'i _TRAILING? _NL

special_block <- _BOL _INDENT? '#+begin_'i name:_GBLOCK_NAME parameters:_block_params? _NL
                 body:_gblock_body
                 _BOL _INDENT? '#+end_'i _GBLOCK_NAME _TRAILING? _NL

# @scanner: _GBLOCK_NAME must NOT be a lesser block name
# (comment, example, export, src, verse — case-insensitive).
# The #+end_ NAME must match the #+begin_ NAME (case-insensitive).

_GBLOCK_NAME  <- [^ \t\n]+
_block_params <- _S _REST_OF_LINE
_gblock_body  <- (_section_element / _blank_line)*

# @semantic: Greater block body may not contain a block of its own
# type (no nested center inside center, etc.).
```

### 6.2 Drawers

```peg
drawer <- _BOL _INDENT? ':' name:_DRAWER_NAME ':' _TRAILING? _NL
          body:_drawer_body
          _BOL _INDENT? ':' 'END'i ':' _TRAILING? _NL

_DRAWER_NAME  <- [A-Za-z0-9_\-]+
_drawer_body  <- (!(_BOL _INDENT? ':' _DRAWER_NAME ':' _TRAILING? _NL) _section_element
                 / _blank_line)*

# @semantic: Drawer body may not contain another drawer (no nesting).
# A :PROPERTIES: drawer outside a valid property-drawer position is
# parsed as an ordinary drawer.
```

### 6.3 Dynamic Blocks

```peg
dynamic_block <- _BOL _INDENT? '#+begin:'i _S name:_DYNBLOCK_NAME
                 parameters:(_S _REST_OF_LINE)? _NL
                 body:_dynblock_body
                 _BOL _INDENT? '#+end:'i _TRAILING? _NL

_DYNBLOCK_NAME  <- [^ \t\n]+
_dynblock_body  <- (_section_element / _blank_line)*

# @semantic: Dynamic block body may not contain another dynamic block.
```

### 6.4 Footnote Definitions

```peg
footnote_definition <- _BOL '[fn:' label:_FN_LABEL ']'
                      first_line:(_S _object*)? _NL
                      body:_fndef_body?

_FN_LABEL     <- [A-Za-z0-9_\-]+
_fndef_body   <- (_section_element / _blank_line)*

# @scanner: Must start at column 0 (unindented).
# first_line captures inline content on the same line as [fn:LABEL].
# body captures subsequent lines as section elements.
# Ends at: next footnote definition, next heading,
# two consecutive blank lines, or end of input.
```

### 6.5 Plain Lists and Items

```peg
plain_list <- _LIST_START item+ _LIST_END

# @scanner: Lists are parsed flat. Nested structure is not emitted as nested
# plain_list nodes; indented items remain siblings and carry indent metadata.

item <- indent:_LISTITEM_INDENT?
        bullet:_bullet
        counter_set:counter_set?
        checkbox:checkbox?
        ( tag:item_tag _NL
        / first_line:_object* _NL )
        body:_item_body?
# After bullet metadata, the rest of the first line is either:
#   - a TAG followed by ' :: ' and then newline, OR
#   - inline content (objects) until end of line.

_bullet <- _unordered_bullet / _ordered_bullet

_unordered_bullet <- ([+\-] / !_BOL '*') _S
# '*' is only a valid list bullet when NOT at column 0.
# @scanner: Column 0 check; '*' at column 0 is always a heading.

_ordered_bullet   <- counter:_COUNTER [.)] _S
_COUNTER          <- [0-9]+ / [a-z]

counter_set <- '[@' _COUNTER ']' _S

checkbox    <- '[' (' ' / 'X' / '-') ']' _S

item_tag    <- _tag_objects ' :: '
# TAG extends to the LAST ' :: ' on the line.
# @scanner: Locate the rightmost ' :: ' on the line
# to split tag from body content.
_tag_objects <- _object+

_item_body  <- (_section_element / _blank_line)*
# @scanner: Item body ends at:
#   1. Next item boundary.
#   2. Two consecutive blank lines.
```

### 6.6 Property Drawers and Node Properties

```peg
property_drawer <- _BOL _INDENT? ':' 'PROPERTIES'i ':' _TRAILING? _NL
                   node_property*
                   _BOL _INDENT? ':' 'END'i ':' _TRAILING? _NL

# Valid positions only (enforced structurally in heading/zeroth_section rules):
#   - Directly after a heading line (no blank lines).
#   - After a heading's planning line (no blank lines).
#   - In the zeroth section (after optional blank lines and comments).
# :PROPERTIES: at any other position is parsed as an ordinary drawer.

node_property <- _BOL _INDENT? ':' name:_PROP_NAME ':' value:(_S _REST_OF_LINE)? _NL

_PROP_NAME <- [^ \t\n:+]+ '+'?
# NAME: non-empty, non-whitespace, not containing ':' or '+'.
# Optional '+' suffix -> append form (NAME+: VALUE appends rather than replaces).
```

### 6.7 Tables

```peg
# --- Org-type table ---
org_table <- table_row+ tblfm:tblfm_line*

table_row <- _BOL _INDENT? '|' (_table_rule_row / _table_std_row) _NL

_table_rule_row <- '-' [^\n]*
# Rule row (separator): '|' followed by '-' and arbitrary characters.

_table_std_row  <- table_cell ('|' table_cell)* '|'?
# Standard row: one or more cells separated by '|'.
# Final '|' may be omitted on the last cell.

table_cell <- _S* _table_cell_objects? _S*
_table_cell_objects <- _object_table+
# Table cell objects: see section 9 for the permitted object set.

tblfm_line <- _BOL _INDENT? '#+TBLFM:'i _S? _REST_OF_LINE _NL

# --- Table.el-type table ---
tableel_table <- _tableel_first_line _tableel_cont_line*

_tableel_first_line <- _BOL _INDENT? '+' '-' [^\n]* _NL
# First line must start with '+-' to distinguish from org-type tables.

_tableel_cont_line  <- _BOL _INDENT? ('|' / '+') [^\n]* _NL
# Continuation lines may start with '|' or '+'.
# Parsed as a raw block. No structured table rows.
# Ends at first line not starting with '|' or '+'.
# @scanner: Lookahead to terminate at non-table lines.
```

---

## 7. Lesser Elements

### 7.1 Lesser Blocks

```peg
_lesser_block <- comment_block / example_block / export_block
               / src_block / verse_block

comment_block <- _BOL _INDENT? '#+begin_comment'i _TRAILING? _NL
                 body:_raw_block_body
                 _BOL _INDENT? '#+end_comment'i _TRAILING? _NL

example_block <- _BOL _INDENT? '#+begin_example'i parameters:_block_params? _NL
                 body:_raw_block_body
                 _BOL _INDENT? '#+end_example'i _TRAILING? _NL

export_block  <- _BOL _INDENT? '#+begin_export'i _S backend:_EXPORT_BACKEND
                 parameters:(_S _REST_OF_LINE)? _NL
                 body:_raw_block_body
                 _BOL _INDENT? '#+end_export'i _TRAILING? _NL

src_block     <- _BOL _INDENT? '#+begin_src'i (_S language:_SRC_LANGUAGE
                 switches:_src_switches? arguments:(_S _REST_OF_LINE)?)? _NL
                 body:_raw_block_body
                 _BOL _INDENT? '#+end_src'i _TRAILING? _NL

verse_block   <- _BOL _INDENT? '#+begin_verse'i _TRAILING? _NL
                 body:_verse_body
                 _BOL _INDENT? '#+end_verse'i _TRAILING? _NL

_EXPORT_BACKEND <- [^ \t\n]+
_SRC_LANGUAGE   <- [^ \t\n]+

_src_switches  <- (_S _src_switch)+
_src_switch    <- '-l' _S '"' [^"]* '"'
               / ('+' / '-') 'n' (_S [0-9]+)?
               / '-r' / '-i' / '-k'

_raw_block_body <- _raw_line*
_raw_line       <- !(_BOL _INDENT? '#+end_'i) [^\n]* _NL
# Raw string. Not parsed for objects.
# Comma-quoting: lines beginning with ',*' or ',#+' have the
# leading ',' stripped by the parser.

_verse_body     <- _verse_line*
_verse_line     <- !(_BOL _INDENT? '#+end_verse'i) _object* _NL
# Verse block contents are parsed as supported objects.
```

### 7.2 Clock

```peg
clock <- _BOL _INDENT? 'CLOCK:'i _S
         ( value:_inactive_range _S duration:_DURATION
         / value:_inactive_ts
         / duration:_DURATION
         ) _TRAILING? _NL

_DURATION <- '=>' _S [0-9]+ ':' [0-9][0-9]
```

### 7.3 Diary Sexp

```peg
diary_sexp <- _BOL '%%' value:('(' _balanced_parens ')') _TRAILING? _NL
# @scanner: Must start at column 0 (unindented).
# Parsed as a raw string; not further decomposed.
```

### 7.4 Planning

```peg
planning <- _BOL _INDENT? _planning_entry (_S _planning_entry)* _TRAILING? _NL
# Planning must immediately follow a heading line (no blank lines).
# Enforced structurally: it appears only in the heading rule.

_planning_entry <- keyword:_PLAN_KW ':' _S value:timestamp
_PLAN_KW        <- 'DEADLINE' / 'SCHEDULED' / 'CLOSED'
# If a keyword is repeated, the last instance wins.
# @semantic: validated during tree interpretation.
```

### 7.5 Comments

```peg
comment <- _comment_line+

_comment_line <- _BOL _INDENT? '#' (' ' value:[^\n]* / &_NL) _NL
# A comment line is '#' followed by a space and content,
# or '#' alone at end of line.
# '#' NOT followed by a space or newline is NOT a comment line.
```

### 7.6 Fixed-Width Areas

```peg
fixed_width <- _fixed_width_line+

_fixed_width_line <- _BOL _INDENT? ':' (' ' value:[^\n]* / &_NL) _NL
# ':' followed by a space and content, or ':' alone at end of line.
# ':' NOT followed by a space or newline is NOT a fixed-width line
# (it could be a drawer start or paragraph text).
```

### 7.7 Horizontal Rules

```peg
horizontal_rule <- _BOL _INDENT? '-----' '-'* _TRAILING? _NL
# A line of at least five consecutive hyphens and nothing else
# (trailing whitespace permitted).
```

### 7.8 Special Keywords

```peg
special_keyword <- _BOL '#+'
                   ( key:_TODO_SPECIAL_KEY ':' value:(_S _REST_OF_LINE)?
                   / key:_SPECIAL_KEY_NO_TODO ':' value:(_S _REST_OF_LINE)? ) _NL
# Recognised in both zeroth and normal sections.
# VALUE is a raw string (not parsed as objects).

_TODO_SPECIAL_KEY   <- 'TODO'i / 'SEQ_TODO'i / 'TYP_TODO'i
_SPECIAL_KEY_NO_TODO <- [A-Za-z][A-Za-z0-9_-]*

# @scanner: When #+TODO: / #+SEQ_TODO: / #+TYP_TODO: is encountered,
# org-todo-keywords-1 must be updated BEFORE any subsequent heading
# is parsed. Heading KEYWORD fields depend on this set.
```

Any `#+KEY: VALUE` matching the key forms above is parsed as `special_keyword`.

### 7.9 Affiliated Keywords

```peg
affiliated_keyword <- caption_keyword
                    / tblname_keyword
                    / results_keyword
                    / plot_keyword

caption_keyword <- _BOL _INDENT? '#+CAPTION'i
                   optval:('[' _caption_optval ']')?
                   ':' value:(_S _object_nofn+)? _NL

tblname_keyword <- _BOL _INDENT? '#+TBLNAME'i
                   ':' value:(_S _REST_OF_LINE)? _NL

results_keyword <- _BOL _INDENT? '#+RESULTS'i
                   ':' value:(_S _REST_OF_LINE)? _NL

plot_keyword    <- _BOL _INDENT? '#+PLOT'i
                   ':' value:(_S _REST_OF_LINE)? _NL

_caption_optval <- (![]\n] . / '[' _caption_optval ']')*
# OPTVAL: any characters except newline; balanced brackets.
# Square brackets must be paired; unbalanced ']' terminates.
# VALUE: supported objects excluding footnote references.

# Multiple affiliated keyword lines may precede one affiliatable element.
# When no affiliatable element immediately follows, the lines fall through
# to paragraph text.
```

### 7.10 Paragraphs

```peg
paragraph <- _paragraph_line+

_paragraph_line <- !_element_boundary _object+ _NL

_element_boundary <- _heading_start
                   / _block_begin
                   / _drawer_start
                   / _dynamic_begin
                   / _fndef_start
                   / _list_bullet_start
                   / _table_line_start
                   / _clock_start
                   / _diary_sexp_start
                   / _comment_line_start
                   / _fixed_width_start
                   / _horizontal_rule_start
                   / _keyword_start

# @scanner: Paragraph termination requires checking all element
# start patterns at the beginning of each line. In tree-sitter,
# this is handled by the GLR parser trying all element alternatives
# (paragraph has the lowest precedence via prec(-1)).
```

**Element boundary lookahead patterns** (used only in `!_element_boundary`):

```peg
_heading_start      <- _BOL '*'+ _S
_block_begin        <- _BOL _INDENT? '#+begin_'i
                     / _BOL _INDENT? '#+begin:'i
_drawer_start       <- _BOL _INDENT? ':' [A-Za-z0-9_\-]+ ':' _TRAILING? _NL
_dynamic_begin      <- _BOL _INDENT? '#+begin:'i
_fndef_start        <- _BOL '[fn:' _FN_LABEL ']'
_list_bullet_start  <- _BOL _INDENT? ([+\-] _S / (!_BOL '*') _S
                     / [0-9]+ [.)] _S / [a-z] [.)] _S)
_table_line_start   <- _BOL _INDENT? ('|' / '+' '-')
_clock_start        <- _BOL _INDENT? 'CLOCK:'i
_diary_sexp_start   <- _BOL '%%('
_comment_line_start <- _BOL _INDENT? '#' (' ' / _NL)
_fixed_width_start  <- _BOL _INDENT? ':' (' ' / _NL)
_horizontal_rule_start <- _BOL _INDENT? '-----'
_keyword_start      <- _BOL _INDENT? '#+'
```

---

## 8. Objects

### 8.1 Export Snippets

```peg
export_snippet <- '@@' backend:_BACKEND ':' value:_snippet_value? '@@'

_BACKEND       <- [A-Za-z0-9\-]+
_snippet_value <- (!'@@' [^\n])+
```

### 8.2 Footnote References

```peg
footnote_reference <- _fn_ref_inline / _fn_ref_anonymous / _fn_ref_labeled
# Ordered so that forms with definitions are tried before the bare label.

_fn_ref_labeled   <- '[fn:' label:_FN_LABEL ']'
_fn_ref_inline    <- '[fn:' label:_FN_LABEL ':' definition:_fn_ref_def ']'
_fn_ref_anonymous <- '[fn::' definition:_fn_ref_def ']'

_fn_ref_def <- _object+
# Supported objects. Square brackets must be balanced within.
# @scanner: Balanced bracket tracking for '[' and ']' inside DEFINITION.

# @semantic: [fn:LABEL] at column 0 on an unindented line is a footnote
# DEFINITION (element), not a reference. Handled by element dispatch
# trying footnote_definition before paragraph/objects.
```

### 8.3 Citations

```peg
citation <- '[cite' style:_cite_style? ':'
            _S? prefix:_cite_global_prefix?
            references:_cite_references
            suffix:_cite_global_suffix?
            _S? ']'

_cite_style   <- '/' style:_STYLE ('/' variant:_VARIANT)?
_STYLE        <- [A-Za-z0-9_\-]+
_VARIANT      <- [A-Za-z0-9_\-/]+

_cite_global_prefix <- _object+ ';'
# Supported objects; balanced brackets; no ';' or '@KEY' subsequences.
# @scanner: Must not contain bare ';' outside balanced brackets,
# and must not contain '@' followed by a citation key pattern.

_cite_references <- citation_reference (';' citation_reference)*

_cite_global_suffix <- ';' _object+
# Same constraints as _cite_global_prefix.
```

### 8.4 Citation References

```peg
# Only inside citations.
citation_reference <- prefix:_cite_key_prefix?
                      '@' key:_CITE_KEY
                      suffix:_cite_key_suffix?

_cite_key_prefix <- _object_min+
# Minimal-set objects; balanced brackets; no ';' or '@KEY' subsequences.

_CITE_KEY <- [A-Za-z0-9\-.:?!\x60'/*@+|(){}<>&_^$#%~]+
# \x60 is the backtick character (`)

_cite_key_suffix <- _object_min+
# Minimal-set objects; balanced brackets; no ';'.
```

### 8.5 Inline Source Blocks

```peg
inline_source_block <- 'src_' language:_INLINE_LANG
                       headers:('[' _inline_headers ']')?
                       '{' body:_inline_body '}'

_INLINE_LANG    <- [^ \t\n\[{]+
_inline_headers <- (![]\n] .)*
# @scanner: Balanced '[' ']' tracking.
_inline_body    <- (![}\n] .)*
# @scanner: Balanced '{' '}' tracking.
```

### 8.6 Line Breaks

```peg
line_break <- !_BOL _PRE_BACKSLASH '\\\\' [ \t]* &_NL
# At the end of an otherwise non-blank line.

_PRE_BACKSLASH <- [^\\]
# The character before '\\' must not be '\'.
# @scanner: This is a lookbehind constraint. The external scanner
# checks the preceding character before emitting the line_break token.
```

### 8.7 Links

#### Radio Links

```peg
radio_link <- &_LINK_PRE _object_min+ &_LINK_POST
# Auto-generated radio-link detection is deferred to post-processing.
# The tree-sitter parser emits radio_target nodes only.
# @scanner: _LINK_PRE is a lookbehind for non-alphanumeric character.
```

#### Plain Links

```peg
plain_link <- &_WORD_PRE type:_LINK_TYPE ':' path:_PATH_PLAIN &_WORD_POST

_LINK_TYPE   <- 'shell' / 'news' / 'mailto' / 'https' / 'http'
              / 'ftp' / 'help' / 'file' / 'elisp'
# @scanner: Configurable via org-link-parameters.

_PATH_PLAIN  <- _path_plain_char+
# Non-whitespace, non-bracket characters; may contain parenthesised
# substrings up to depth 2.
# Must end with: non-punctuation non-whitespace char, '/', or '(...)'.
_path_plain_char <- [^ \t\n\[\]<>()]
                  / '(' ([^ \t\n\[\]<>()] / '(' [^ \t\n\[\]<>()]* ')')* ')'

# @scanner: _WORD_PRE / _WORD_POST are lookbehind/lookahead for
# non-word-constituent character.
```

#### Angle Links

```peg
angle_link <- '<' type:_LINK_TYPE ':' path:_PATH_ANGLE '>'

_PATH_ANGLE <- [^>]*
# Any characters except '>'.
# Newlines and indentation within the path are ignored (stripped)
# during tree interpretation.
# @semantic: Whitespace normalisation in post-processing.
```

#### Regular Links

```peg
regular_link <- '[[' path:_link_path ']]'
              / '[[' path:_link_path '][' description:_link_description ']]'

_link_path <- (_link_path_char / '\\]' / '\\\\')*
_link_path_char <- [^\[\]\\]
# Path types (determined by content pattern):
#   FILENAME            -> file link
#   LINKTYPE:PATHINNER  -> typed link
#   LINKTYPE://PATHINNER -> typed link
#   id:ID               -> id link
#   #CUSTOM-ID          -> custom-id link
#   (CODEREF)           -> coderef link
#   FUZZY               -> fuzzy link
# @semantic: Path type classification is a post-processing step.
# Whitespace sequences inside PATHREG are normalised to a single space.

_link_description <- (!']]' _object_min)+
# Minimal-set objects plus export snippets, inline source blocks
# (both already in the minimal set).
# May contain '[' but not ']]'.
# May contain a plain or angle link.
# The negative lookahead !']]' prevents consuming into the link's
# closing delimiter.
```

### 8.8 Targets and Radio Targets

```peg
target <- '<<' value:_TARGET_TEXT '>>'

_TARGET_TEXT <- !_WS [^<>\n]+ !_WS
# Any characters except '<', '>', newline.
# Must not start or end with whitespace.

radio_target <- '<<<' body:_radio_target_body '>>>'

_radio_target_body <- !_WS _object_min+ !_WS
# Minimal-set objects.
# Must start and end with non-whitespace.
# No '<', '>', newline.
# Defines an auto-link: every matching text occurrence becomes a radio link.
```

### 8.9 Timestamps

```peg
timestamp <- _active_range / _inactive_range
           / _active_range_sameday / _inactive_range_sameday
           / _active_ts / _inactive_ts
# Ranges tried first (greedy); they contain '--' between two timestamps
# that would otherwise individually match _active_ts / _inactive_ts.
# Sexp timestamps are excluded (see section 11).

# --- Active ---
_active_ts  <- '<' _ts_inner '>'
_active_range <- '<' _ts_inner '>' '--' '<' _ts_inner '>'
_active_range_sameday <- '<' _ts_date _S _ts_time '-' _ts_time
                         (_S _ts_modifiers)? '>'

# --- Inactive ---
_inactive_ts  <- '[' _ts_inner ']'
_inactive_range <- '[' _ts_inner ']' '--' '[' _ts_inner ']'
_inactive_range_sameday <- '[' _ts_date _S _ts_time '-' _ts_time
                           (_S _ts_modifiers)? ']'

# --- Internal structure ---
_ts_inner <- date:_ts_date (time:(_S _ts_time))? (modifiers:(_S _ts_modifiers))?

_ts_date  <- year:_YYYY '-' month:_MM '-' day:_DD dayname:(_S _ts_dayname)?
_YYYY     <- [0-9][0-9][0-9][0-9]
_MM       <- [0-9][0-9]
_DD       <- [0-9][0-9]
_ts_dayname <- [^ \t\n+\-\]>0-9]+
# DAYNAME: optional non-whitespace excluding '+', '-', ']', '>', digits, newline.

_ts_time  <- [0-9][0-9]? ':' [0-9][0-9]
# H:MM — H is 1-2 digits, MM is exactly 2 digits.

_ts_modifiers <- (_ts_repeater (_S _ts_delay)? / _ts_delay (_S _ts_repeater)?)
# Zero or one repeater AND/OR zero or one delay, in either order.

_ts_repeater <- mark:_REPEATER_MARK value:[0-9]+ unit:_TIME_UNIT
                ('/' cap_value:[0-9]+ cap_unit:_TIME_UNIT)?
# Optional upper-bound: MARK VALUE UNIT / VALUE UNIT

_REPEATER_MARK <- '++' / '.+' / '+'
# '+'  cumulative
# '++' catch-up
# '.+' restart

_ts_delay <- mark:_DELAY_MARK value:[0-9]+ unit:_TIME_UNIT

_DELAY_MARK <- '--' / '-'
# '-'  all type
# '--' first type

_TIME_UNIT <- [hdwmy]
```

### 8.10 Text Markup

```peg
bold           <- &_MARKUP_PRE '*' body:_markup_body '*' &_MARKUP_POST
italic         <- &_MARKUP_PRE '/' body:_markup_body '/' &_MARKUP_POST
underline      <- &_MARKUP_PRE '_' body:_markup_body '_' &_MARKUP_POST
strike_through <- &_MARKUP_PRE '+' body:_markup_body '+' &_MARKUP_POST
verbatim       <- &_MARKUP_PRE '=' body:_verbatim_body '=' &_MARKUP_POST
code           <- &_MARKUP_PRE '~' body:_code_body '~' &_MARKUP_POST

_markup_body   <- !_WS _object (!_WS / &_object) _object* !_WS
# CONTENTS: supported objects; must not start or end with whitespace.
# Each _object inside _markup_body uses the full _object set
# (see section 9, "Object Containers").

_verbatim_body <- [^ \t\n=] [^\n=]* [^ \t\n=]
               / [^ \t\n=]
# Raw string (not parsed for objects).
# Must not start or end with whitespace.
# Must not contain '=' (the closing marker).

_code_body     <- [^ \t\n~] [^\n~]* [^ \t\n~]
               / [^ \t\n~]
# Same rules as _verbatim_body but excludes '~' instead of '='.
# Single non-whitespace character is valid for both.

_MARKUP_PRE  <- [ \t\-({'"]       / _BOL
# @scanner: _MARKUP_PRE is a lookbehind constraint.
# Character preceding the opening marker must be one of:
# whitespace, '-', '(', '{', "'", '"', or beginning of line.

_MARKUP_POST <- [ \t\n\-.,;:!?')\}\["\\] / _EOL
# Character following the closing marker must be one of:
# whitespace, '-', '.', ',', ';', ':', '!', '?', "'",
# ')', '}', '[', '"', '\', or end of line.
```

### 8.11 Plain Text

```peg
plain_text <- (!_object_starter .)+
# Any characters not matched by another object type.
# @semantic: Whitespace within plain text is collapsed to a single
# space during tree interpretation (e.g., "hello\n  there" -> "hello there").

# _object_starter is the set of characters/sequences that could begin
# any non-plain-text object. Used as negative lookahead so that
# plain_text does not consume the start of a real object.
# @scanner: In practice, the external scanner emits plain_text tokens
# by scanning forward until it hits a potential object boundary.
```

---

## 9. Object Sets

Five object sets are used, differentiated by what the containing context
permits. In all cases, recursive markup types (`bold`, `italic`,
`underline`, `strike_through`) internally contain `_object` (the full
set), regardless of which set the markup type itself appears in. This
matches the Org spec: containment restrictions apply only to the
**direct children** of a container.

```peg
# --- Full supported set ---
# Used in: paragraphs, verse blocks, item tags, heading titles*,
#          caption values*, footnote ref definitions, citation globals,
#          recursive markup body.
# (* = with noted exclusion below)
_object <- export_snippet
         / footnote_reference
         / citation
         / inline_source_block
         / line_break
         / regular_link / angle_link / plain_link
         / target / radio_target
         / timestamp
         / bold / italic / underline / strike_through
         / verbatim / code
         / plain_text

# --- Full set, no line breaks ---
# Used in: heading TITLE.
_object_nolb <- export_snippet
              / footnote_reference
              / citation
              / inline_source_block
              / regular_link / angle_link / plain_link
              / target / radio_target
              / timestamp
              / bold / italic / underline / strike_through
              / verbatim / code
              / plain_text

# --- Full set, no footnote references ---
# Used in: #+CAPTION: VALUE.
_object_nofn <- export_snippet
              / citation
              / inline_source_block
              / line_break
              / regular_link / angle_link / plain_link
              / target / radio_target
              / timestamp
              / bold / italic / underline / strike_through
              / verbatim / code
              / plain_text

# --- Minimal set ---
# Used in: citation ref prefix/suffix, link descriptions,
#          radio target body, radio link body.
_object_min <- export_snippet
             / inline_source_block
             / line_break
             / regular_link / angle_link / plain_link
             / target / radio_target
             / timestamp
             / bold / italic / underline / strike_through
             / verbatim / code
             / plain_text

# --- Table cell set ---
# Minimal + citations + footnote references.
# Equivalent to the full set minus line_break (line breaks have no
# meaning inside a table cell).
_object_table <- export_snippet
               / footnote_reference
               / citation
               / inline_source_block
               / regular_link / angle_link / plain_link
               / target / radio_target
               / timestamp
               / bold / italic / underline / strike_through
               / verbatim / code
               / plain_text
```

**Object containers and their permitted child sets** (summary):

| Container | Direct-child object set |
|-----------|------------------------|
| Paragraph, verse block | `_object` |
| Heading TITLE | `_object_nolb` |
| Item TAG | `_object` |
| `#+CAPTION:` VALUE | `_object_nofn` |
| Bold / italic / underline / strike-through body | `_object` |
| Verbatim / code body | raw string (no objects) |
| Regular link DESCRIPTION | `_object_min` |
| Radio link / radio target | `_object_min` |
| Footnote reference DEFINITION | `_object` |
| Citation GLOBALPREFIX / GLOBALSUFFIX | `_object` |
| Citation reference KEYPREFIX / KEYSUFFIX | `_object_min` |
| Table cell | `_object_table` (full set minus line breaks) |
| Planning timestamp | timestamp only |
| Clock | inactive timestamp only |

---

## 10. Lexical Primitives

```peg
_S          <- [ \t]+                  # one or more horizontal whitespace
_WS         <- [ \t\n]                 # single whitespace character (incl. newline)
_NL         <- '\n' / _EOI            # newline or end of input
_EOL        <- &_NL                    # at end of line (lookahead)
_BOL        <- # beginning of line: after '\n' or at start of input
               # @scanner: emitted by external scanner
_EOI        <- !.                      # end of input
_INDENT     <- [ \t]+                  # leading whitespace (indentation)
_TRAILING   <- [ \t]+                  # trailing whitespace before newline
_REST_OF_LINE <- [^\n]+                # all characters to end of line
_blank_line <- _BOL [ \t]* _NL        # line with only whitespace

_balanced_parens   <- (!'(' !')' [^\n] / '(' _balanced_parens ')')*
_balanced_brackets <- (!'[' !']' [^\n] / '[' _balanced_brackets ']')*
_balanced_braces   <- (!'{' !'}' [^\n] / '{' _balanced_braces '}')*

_WORD_PRE  <- [^A-Za-z0-9]  / _BOL    # non-word-constituent or start of line
_WORD_POST <- [^A-Za-z0-9]  / _EOL    # non-word-constituent or end of line
_LINK_PRE  <- [^A-Za-z0-9]  / _BOL    # non-alphanumeric or start of line
_LINK_POST <- [^A-Za-z0-9]  / _EOL    # non-alphanumeric or end of line
```

---

## 11. Excluded Features

The following features are explicitly excluded from the target syntax.
All are treated as plain text by the parser. Their syntax is documented
here for future expansion.

### 11.1 Entities

```peg
# \NAME POST  |  \NAME{}  |  \_SPACES
# _entity      <- '\\' _ENTITY_NAME (_ENTITY_POST / '{}')
# _ENTITY_NAME <- [A-Za-z]+      # must be in org-entities / org-entities-user
# _ENTITY_POST <- [^A-Za-z] / _EOL
```

### 11.2 LaTeX Fragments

```peg
# Command:    \NAME BRACKETS*
# _latex_cmd       <- '\\' [A-Za-z]+ '*'?
#                     ('[' [^\[\]{}\n]* ']' / '{' [^{}\n]* '}')*

# Inline math: \(CONTENTS\)  |  \[CONTENTS\]
# _latex_inline    <- '\\(' (!'\\)' .)* '\\)'
#                   / '\\[' (!'\\]' .)* '\\]'

# TeX dollar:  $$CONTENTS$$  |  $CHAR$  |  $BORDER BODY BORDER$
# _latex_dollar    <- '$$' (!'$$' .)* '$$'
#                   / '$' [^ \t\n.,?;"$] '$'
#                   / '$' _dollar_border [^\n$]* _dollar_border '$'
# _dollar_border   <- [^ \t\n.,;$]
```

### 11.3 LaTeX Environments

```peg
# \begin{NAME} CONTENTS \end{NAME}
# _latex_env <- '\\begin{' [A-Za-z0-9*]+ '}'
#               (!'\\end{' .)*
#               '\\end{' [A-Za-z0-9*]+ '}'
```

### 11.4 Babel Calls

```peg
# #+call: NAME[HEADER1](ARGUMENTS)[HEADER2]
# _babel_call <- _BOL _INDENT? '#+call:'i _S
#                [^ \t\n\[\]()]+ ('[' [^\]\n]* ']')?
#                '(' [^)\n]* ')' ('[' [^\]\n]* ']')? _NL
```

### 11.5 Inline Babel Calls

```peg
# call_NAME[HEADER](ARGUMENTS)[HEADER2]
# _inline_babel <- 'call_' [^ \t\n\[\]()]+
#                  ('[' [^\]\n]* ']')?
#                  '(' [^)\n]* ')'
#                  ('[' [^\]\n]* ']')?
```

### 11.6 Macros

```peg
# {{{NAME}}}  |  {{{NAME(ARGUMENTS)}}}
# _macro <- '{{{' [A-Za-z] [A-Za-z0-9_\-]* ('(' (!'}}}' .)* ')')? '}}}'
```

### 11.7 Subscript and Superscript

```peg
# CHAR_SCRIPT (subscript)  |  CHAR^SCRIPT (superscript)
# _subscript   <- [^ \t\n] '_' _SCRIPT
# _superscript <- [^ \t\n] '^' _SCRIPT
# _SCRIPT <- '*'
#           / '{' _balanced_braces '}'
#           / '(' _balanced_parens ')'
#           / [+\-]? [A-Za-z0-9,.]* [A-Za-z0-9]
```

### 11.8 Sexp Timestamps

```peg
# <%%(SEXP)>
# _sexp_timestamp <- '<%%(' _balanced_parens ')'
#                    (_S _ts_time ('-' _ts_time)?)? '>'
```

---

## 12. External Scanner Requirements

Tree-sitter's pure grammar (context-free with precedence) cannot handle
several aspects of Org syntax. These require an **external scanner** — a
C/C++ module that emits tokens based on state not expressible in the
grammar DSL.

### 12.1 Heading Level Tracking

**Problem:** A heading at level N may only contain sub-headings at
level > N. The grammar's `heading*` is recursive, but the parser must
close a heading when a same-or-higher-level heading is encountered.

**Scanner token:** `_HEADING_END` — emitted when the next line begins
with `*`-count <= current heading level, or at end of input.

### 12.2 Indentation and List Nesting

**Problem:** Org lists are indentation-sensitive, but this parser keeps list
structure flat for stability and recovery. Nested hierarchy is reconstructed
later from indent metadata.

**Scanner tokens:**
- `_LIST_START` / `_LIST_END` — bracket a plain list.
- `_LISTITEM_INDENT` — emits per-item indentation for post-processing.
- `_ITEM_END` — emitted when item-boundary rules terminate an item.

### 12.3 TODO Keyword Set

**Problem:** The set of valid TODO keywords is configurable per-document
via `#+TODO:` / `#+SEQ_TODO:` / `#+TYP_TODO:` in the zeroth section.
Headings parsed after these keywords must use the updated set.

**Scanner behaviour:** Maintain a mutable keyword list (initially
`["TODO", "DONE"]`). When a `#+TODO:` special keyword is parsed,
update the list. When scanning a heading line, check the word after
stars against this list to decide whether it is a `_TODO_KW` token.

### 12.4 Block End Matching

**Problem:** `#+end_NAME` must match the `#+begin_NAME` that opened the
block (case-insensitive). The grammar cannot express this cross-reference.

**Scanner behaviour:** Push block names onto a stack at `#+begin_`. When
`#+end_` is encountered, verify the name matches the top of the stack.

### 12.5 Markup Boundary Lookbehind

**Problem:** Text markup requires a PRE character (whitespace, `-`, `(`,
`{`, `'`, `"`, or BOL) immediately before the opening marker. PEG and
tree-sitter grammars do not support lookbehind.

**Scanner behaviour:** Track the previous character. When an opening
markup marker is encountered, verify the preceding character satisfies
the PRE constraint. Emit the marker token only if the constraint holds.

### 12.6 Paragraph Termination

**Problem:** A paragraph line must not begin with a pattern that starts
another element. In tree-sitter's GLR parser, this is handled by
precedence (paragraph gets `prec(-1)`), but an external scanner can
improve accuracy by explicitly checking element-start patterns.

**Scanner behaviour:** At each line boundary, check whether the upcoming
line starts an element. If so, do not emit `_PARAGRAPH_CONTINUE`.

### 12.7 Footnote Definition and Item Termination

**Problem:** Footnote definitions and list items terminate at two
consecutive blank lines. The blank lines belong to the item/definition,
not to any inner element.

**Scanner behaviour:** Count consecutive blank lines. When the count
reaches 2, emit `_FNDEF_END` or `_ITEM_END`.

### 12.8 Column-Zero Constraints

**Problem:** Headings, footnote definitions, and diary sexps must start
at column 0.

**Scanner token:** `_BOL` is emitted with column information. Rules
requiring column 0 check this value.

### 12.9 Item Tag (Last `::` Matching)

**Problem:** The item tag extends to the **last** ` :: ` on the line.
PEG greedily matches left-to-right and cannot inherently find the
rightmost match.

**Scanner behaviour:** When parsing an item line, scan ahead to find the
rightmost ` :: ` and emit `_ITEM_TAG_END` at that position.

### 12.10 Radio Link Detection

**Problem:** Radio links are auto-generated wherever text matches a
radio target's content. This requires knowledge of all radio targets
in the document.

**Implementation status:** Deferred to post-processing (Python layer).
The parser emits `radio_target` nodes, but does not auto-detect
`radio_link` spans during parsing.

---

## Appendix A: Named Node Summary

All named nodes that appear in the concrete syntax tree, grouped by
category.

**Document structure:**
`document`, `zeroth_section`, `heading`, `section`

**Greater elements:**
`center_block`, `quote_block`, `special_block`, `drawer`,
`dynamic_block`, `footnote_definition`, `plain_list`, `item`,
`property_drawer`, `node_property`, `org_table`, `tableel_table`,
`table_row`, `table_cell`

**Lesser elements:**
`comment_block`, `example_block`, `export_block`, `src_block`,
`verse_block`, `clock`, `diary_sexp`, `planning`, `comment`,
`fixed_width`, `horizontal_rule`, `special_keyword`,
`caption_keyword`, `tblname_keyword`, `results_keyword`,
`plot_keyword`, `paragraph`

**Objects:**
`export_snippet`, `footnote_reference`, `citation`,
`citation_reference`, `inline_source_block`, `line_break`,
`regular_link`, `angle_link`, `plain_link`,
`target`, `radio_target`, `timestamp`, `completion_counter`,
`bold`, `italic`, `underline`, `strike_through`,
`verbatim`, `code`, `plain_text`

**Heading sub-nodes:**
`stars`, `todo_keyword`, `priority`, `tags`, `tag`

**Item sub-nodes:**
`counter_set`, `checkbox`, `item_tag`

**Planning sub-node:**
`tblfm_line`
