# Section-Scoped Indent Blocks Plan

## Objective

Replace element-local indentation handling with section-scoped `block` nodes
that explicitly represent indentation structure in the syntax tree.

This plan applies to both:

- `zeroth_section`
- heading `section` bodies

and leaves heading hierarchy (`*`, `**`, etc.) unchanged.

## Decisions Confirmed

- Blank lines may separate blocks.
- Top-level section content with zero indent should not be forced into a
  `block` wrapper.
- `block.indent` must preserve raw leading whitespace text (spaces/tabs),
  without normalization at parse time.

## Target AST Model

## New node: `block`

`block` represents a contiguous region of section content that begins at a
non-zero indentation level and may contain nested `block` nodes.

Expected shape:

```scm
(block
  indent: (indent)
  body: (...section content...)
  body: (block ...)
  body: (...section content...))
```

Key properties:

- `indent` is the opening line's raw leading whitespace.
- A `block` is section-local (never crosses section boundaries).
- `block` nesting is indentation-driven by scanner state.
- Blank lines are not part of `block` body ownership by default; they can occur
  between adjacent blocks/elements at section level.

## Section content model

Section content becomes a sequence of:

- section elements (no explicit grammar-level `indent` prefixes),
- `block` nodes,
- blank lines.

Top-level (zero-indent) elements remain directly inside `section` /
`zeroth_section`.

## Scope of Change

## Grammar (`tree-sitter-org/grammar.js`)

1. Add `block` rule with explicit `indent` field and repeatable `body` field.
2. Refactor section rules to parse content via a block-aware dispatcher.
3. Remove element-level indentation fields and closing-indent fields from:
   - drawers/logbook/property drawers,
   - greater/lesser blocks,
   - lists/list items,
   - fixed-width/comment/diary and other section elements currently carrying
     `optional(field('indent', $.indent))` or similar.
4. Keep element syntax otherwise intact (content rules remain element-specific).
5. Make paragraph parse a strict fallback line element when no stronger element
   starter matches.

## Scanner (`tree-sitter-org/src/scanner.c`)

1. Add block-control external tokens, e.g.:
   - `TOKEN_BLOCK_START` (or equivalent)
   - `TOKEN_BLOCK_END` (or equivalent)
   - optional section-sync token if needed for state reset boundaries.
2. Track section-local indentation stack in scanner state.
3. At beginning-of-line in section contexts:
   - measure raw leading whitespace,
   - compare indentation depth against stack top,
   - emit block open/close tokens accordingly,
   - preserve measured raw indent lexeme for `block.indent`.
4. Ensure heading/zeroth transitions reset block state.
5. Decouple element classification from leading whitespace consumption where
   possible so elements parse as if line prefix ownership is scanner-managed.

## Parser artifacts

Because this changes external tokens and grammar structure, regenerate:

- `src/parser.c`
- `src/grammar.json`
- `src/node-types.json`
- `src/tree_sitter/*`

using `npm run build` / `npm run generate` as appropriate.

## Behavioral Rules

## Block ownership rules

- A block starts when an indented line appears in section content and that
  indent is greater than current block depth.
- A block ends when a subsequent non-blank line has smaller indentation than
  the active block depth.
- Equal indentation continues in the same block level.
- Deeper indentation opens nested block(s).

## Element start indent rule

Element identity is determined by its own start line syntax. The opening
indentation line determines initial placement in block hierarchy.

For multiline elements (drawers/blocks/etc.):

- they remain a single element once started,
- internal lines do not force structural reassignment,
- trailing lines may dedent relative to start without splitting ownership,
  per requested behavior.

## Blank lines

- Blank lines may appear between top-level elements and blocks.
- Blank lines may terminate or separate adjacent block regions implicitly by
  allowing the next non-blank line to re-establish indentation context.
- We should avoid requiring blank lines to be nested under blocks unless there
  is a compelling parser conflict reason.

## Paragraph strategy

Paragraph becomes the last-resort element for section lines.

Design intent:

- Other element starters get precedence.
- Paragraph claims a line only when it is not a recognized starter for any
  stronger element.
- Prefer line-oriented paragraph matching to reduce cross-line ambiguity.
- Multi-line paragraph semantics can be recovered in Python layer by merging
  adjacent paragraph line nodes if needed.

## Detailed Implementation Phases

## Corpus-first expectation updates (critical)

Before or alongside scanner/grammar refactors, update focused corpus expectations
early for each migrated behavior slice. Do not defer corpus updates until the
end of implementation.

Rationale:

- This migration intentionally changes AST shape (`block` wrappers,
  removed element-level `indent` fields).
- Keeping stale expectations hides whether failures are real regressions or
  simply expected shape changes.
- Early corpus alignment gives immediate feedback on parser/scanner decisions
  and prevents long debugging cycles on outdated trees.

Execution guidance:

- For each phase, start with a small, representative corpus subset and update
  expected trees first.
- Keep updates incremental by syntax area (`sections` -> `drawers` -> `lists`
  -> `blocks`) so breakage remains attributable.
- Run focused `tree-sitter test --file-name ...` after every slice before
  expanding scope.

## Phase 1: Introduce block scaffolding

1. Add new external tokens and scanner state serialization support.
2. Add `block` grammar rule and wire into section content choices.
3. Keep existing element indent fields temporarily to reduce blast radius while
   proving block open/close correctness.
4. Add focused corpus fixture(s) for nested block skeleton behavior.
5. Update existing section corpus expectations early where wrapper shape is
   intentionally changing.

Exit criteria:

- grammar generates,
- scanner compiles,
- focused section/block tests pass.

## Phase 2: Migrate indentation ownership to blocks

1. Remove per-element `indent` and `closing_indent` fields in grammar.
2. Update affected element rules to parse without leading-indent responsibility.
3. Adjust scanner line-start behavior so element matching works after block
   prefix handling.

Exit criteria:

- no element depends on direct `optional(field('indent', $.indent))`,
- expected elements still recognized under indentation.

## Phase 3: Paragraph fallback hardening

1. Simplify paragraph to fallback-first strategy.
2. Ensure paragraph does not steal indented drawer/block/list/timestamp/link
   starts.
3. Validate previously unstable cases (drawers, list-adjacent content,
   indented hash comments, indented timestamps/links).

Exit criteria:

- regressions in known ambiguity suites eliminated,
- requested indented paragraph cases represented inside `block` structure.

## Phase 4: Corpus and semantic migration

1. Update corpus expectations broadly for `block` wrappers and removed element
   indent fields.
2. Update Python semantic mapping to consume `block` hierarchy and recover
   effective indentation semantics.
3. Keep backward-compatibility adapters where practical (or document breakage).

Exit criteria:

- full `tree-sitter test` passes,
- Python checks pass (`poetry run task check`) after parser/library updates.

## Affected Corpus Areas

High-impact files likely to require updates:

- `test/corpus/sections.txt`
- `test/corpus/lists.txt`
- `test/corpus/drawers.txt`
- `test/corpus/greater_blocks.txt`
- `test/corpus/lesser_blocks.txt`
- `test/corpus/clocks.txt`
- any corpus files asserting element-level `indent` fields.

Priority order for early migration:

1. `test/corpus/sections.txt`
2. `test/corpus/drawers.txt`
3. `test/corpus/lists.txt`
4. `test/corpus/greater_blocks.txt`
5. `test/corpus/lesser_blocks.txt`

## Verification Plan

## Grammar/scanner cycle

From `tree-sitter-org/`:

```bash
npm run generate
npm run build
tree-sitter test
```

During iteration, run focused suites first:

```bash
tree-sitter test --file-name sections.txt
tree-sitter test --file-name drawers.txt
tree-sitter test --file-name lists.txt
tree-sitter test --file-name greater_blocks.txt
tree-sitter test --file-name lesser_blocks.txt
```

## Repository-level checks

From repo root after parser stabilization:

```bash
poetry run task check
```

If grammar/scanner changed, rebuild shared library before Python tests:

```bash
(cd tree-sitter-org && tree-sitter build)
```

## Risks and Mitigations

## Risk: scanner complexity/state bugs

Mitigation:

- keep block state minimal (indent stack + section reset),
- serialize/deserialize carefully,
- add corpus tests that stress transitions (dedent, sibling blocks,
  section boundary resets).

## Risk: conflicts with list scanner state

Mitigation:

- define clear precedence and ordering between list-control and block-control
  tokens,
- add targeted list+indent block tests before broad corpus updates.

## Risk: multiline element boundary drift

Mitigation:

- anchor ownership to element start line,
- do not let internal dedent split an active multiline element,
- add explicit drawer/block spanning tests for dedent scenarios.

## Risk: large AST breaking change

Mitigation:

- perform migration in phases,
- keep semantic recovery layer adaptation explicit,
- document transition expectations for downstream consumers.

## Deliverables

1. Grammar/scanner implementation of section-scoped `block` nodes.
2. Updated corpus with explicit block structure assertions.
3. Updated semantic layer behavior for block-aware indentation recovery.
4. Passing `tree-sitter test` and `poetry run task check`.
