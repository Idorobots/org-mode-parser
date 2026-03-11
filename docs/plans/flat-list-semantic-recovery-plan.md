# Flat List Parsing + Semantic Recovery Plan

## Goal

Make list parsing resilient by keeping syntax parsing line-oriented and moving
list body/continuation ownership to semantic analysis. This removes most parser
ambiguity around indented lines (especially `+` bullets vs markup) while
preserving rich list structure in the Python API.

## Current Pain Points

- Grammar-level `item_continuation_line` competes with other indented elements
  (paragraphs, drawers, blocks, fixed-width, tables, planning lines).
- Indented `+` list lines are ambiguous with strike markup openers in scanner
  and object parsing paths.
- Small precedence changes can regress unrelated element categories.

## Target Model

- Concrete tree (`tree-sitter`):
  - Parse each bullet line as one `list_item` node.
  - Do not attach continuation/body nodes under `list_item` in grammar.
  - Preserve leading list indentation via `indent` field on `list_item`.
- Semantic tree (`src/org_parser/document/...`):
  - Reconstruct nested lists by indentation.
  - Reattach indented non-list nodes as list item body when applicable.
  - Handle indented paragraphs explicitly and deterministically.

---

## Phase 1: Grammar Simplification

1. Simplify `tree-sitter-org/grammar.js` list rules:
   - Keep `list_item` as: `indent? + bullet + counter/checkbox + first-line + NL`.
   - Remove `_item_body` and `item_continuation_line` from `list_item`.
2. Keep list items as section elements (`_affiliatable` / `_zs_element` paths).
3. Preserve existing `indent` field node shape to avoid downstream breakage.
4. Regenerate artifacts (`npm run generate`).

Success criteria:
- No list continuation parsing in grammar.
- Corpus parses list lines as sibling `list_item` nodes without `ERROR` for the
  nested `+` checkbox case.

---

## Phase 2: Scanner Tightening (Minimal)

1. Keep scanner focused on bullet starts and element boundaries.
2. Remove heuristics that attempt to classify continuation lines as list-owned
   content.
3. Ensure `+` at list-line start prefers bullet tokenization over markup-open
   when followed by required list spacing.

Success criteria:
- `  + [X] ...` lines consistently tokenize as list item starts.
- No new scanner-side coupling to continuation semantics.

---

## Phase 3: Semantic Recovery Algorithm

Implement recovery in document construction (where CST is transformed into
domain objects).

### 3.1 Inputs

- Flat ordered stream of section nodes (`list_item`, `paragraph`, `fixed_width`,
  drawers, blocks, tables, blank lines, etc.).
- Per-node indentation width (spaces/tabs normalized consistently with existing
  parser behavior).

### 3.2 Core State

- `list_stack`: stack of active list levels with indent width.
- `current_item_at_level`: last item emitted per level.
- `pending_blank_lines`: count of blank lines since last structural node.

### 3.3 Nesting Rules

- New `list_item` with indent `i`:
  - if stack empty -> start top-level list.
  - if `i` > current level indent -> nest under previous item.
  - if `i` == current level indent -> sibling at same level.
  - if `i` < current level indent -> pop until matching/parent level, then add.
- If no exact level exists after popping, attach at nearest parent level and
  start a new sublist level for `i`.

### 3.4 Body Attachment Rules (Including Indented Paragraphs)

For a non-`list_item` node `N` with indent `j` following a list context:

1. If no active list item exists: `N` remains a normal section node.
2. If `j` > indent of the most recent list item at top stack level:
   - Attach `N` as body of that list item.
3. If `N` is a `paragraph` and every line in `N` is indented deeper than the
   owner item indent:
   - Attach as list item continuation paragraph body.
4. If `N` is a `paragraph` with mixed indentation:
   - Split behavior (preferred): attach only fully-indented leading segment;
     keep remainder at section level.
   - Fallback (acceptable first iteration): keep whole paragraph at section
     level to avoid incorrect ownership.
5. Blank lines:
   - Single blank line does not automatically terminate list ownership.
   - Two+ blank lines terminate attach-to-item mode unless followed by deeper
     indented content.

### 3.5 Termination Rules

- Encountering a non-indented (or shallower-than-item) non-list element closes
  attachment to the deeper item level.
- Heading boundary always clears list recovery state.

---

## Phase 4: Paragraph Indent Handling Details

Add a small helper in semantic layer:

- `compute_min_indent(paragraph_node) -> int | None`
  - Determine minimum visual indent across non-blank paragraph lines.
  - Ignore empty/whitespace-only lines.

Use it to classify paragraph ownership:

- `min_indent > item_indent` => continuation paragraph body.
- `min_indent <= item_indent` => paragraph is not item body.

Tab policy:

- Reuse existing scanner/display-column behavior for tabs. Do not invent a new
  tab-width policy in semantics.

---

## Phase 5: Test Plan

1. Corpus updates (`tree-sitter-org/test/corpus/lists.txt`):
   - Keep new edge case with nested `+` checkboxes.
   - Update expectations to flat `list_item` CST where needed.
2. Add semantic-level tests in Python (`tests/...`):
   - Nested list reconstruction by indent.
   - Indented continuation paragraph attachment.
   - Mixed-indent paragraph behavior.
   - Blank-line-separated continuation behavior.
3. Run full gates:
   - `npm test` in `tree-sitter-org/`
   - `tree-sitter build`
   - `poetry run task check` in repo root.

---

## Rollout Strategy

1. Land grammar/scanner simplification first with CST-focused corpus updates.
2. Land semantic recovery in a second commit with Python tests.
3. Keep an interim compatibility shim if any existing API expects
   grammar-attached item bodies.

---

## Risks and Mitigations

- Risk: over-attaching unrelated indented paragraphs to list items.
  - Mitigation: strict `min_indent > item_indent` rule and heading/boundary
    reset.
- Risk: behavior changes for drawers/blocks after lists.
  - Mitigation: explicit element precedence in semantic attachment (block-like
    nodes require deeper indent to attach).
- Risk: regressions hidden by corpus normalization.
  - Mitigation: add semantic tests that assert reconstructed hierarchy, not just
    CST shape.

## Definition of Done

- Nested `+` checkbox case parses without `ERROR` nodes.
- Full tree-sitter corpus passes.
- Semantic list reconstruction produces expected nested/body structure,
  including indented paragraph continuations.
- `poetry run task check` passes.
