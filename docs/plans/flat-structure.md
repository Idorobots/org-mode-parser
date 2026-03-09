## Goal

Make parse output intentionally flatter so semantic node construction can own:

- line boundary semantics (newlines and blank lines)
- indentation-based nesting recovery
- higher-level text reconstruction in titles and paragraphs

The grammar should keep recognizing Org syntax correctly, but expose enough low-level structure for semantic reconstruction to be deterministic and robust.

---

## Current state and constraints

The repository already leans in this direction:

1. Lists are intentionally parsed flat. `plain_list` contains sibling `item` nodes, and `item_indent` stores indentation for post-processing.
2. Section bodies are flat sequences (`_section_element` and `_blank_line`).
3. ROADMAP already includes `Bind indent in lesser/greater elements` and `Recover list & element nesting`.

Current gaps:

- `_NL` and `_blank_line` are anonymous, so semantic constructors cannot read line boundaries as nodes.
- Only list items consistently expose indentation (`item_indent`); most section-level elements do not.
- Paragraph continuation logic is still parser/scanner-heavy (`_PARAGRAPH_CONTINUE`).

---

## Validation of the previous plan

The direction is correct, but two parts were too broad/risky:

1. Global `_NL -> newline` rename everywhere would flood the tree with low-value newline nodes (headings, keyword delimiters, block delimiters) and create very large corpus churn.
2. Adding a new `_ELEMENT_INDENT` external scanner token is likely unnecessary in the first iteration; existing `_INDENT` regex can be exposed via fields in most places.

Also, `_PARAGRAPH_CONTINUE` should not be removed early. Semantic reconstruction runs after parse and cannot replace parser-time disambiguation until we prove equivalent behavior.

---

## Revised implementation plan

### Phase 1: Expose line separators in a targeted way

Use aliases instead of global renames.

- Keep `_NL` private.
- In content-bearing contexts, expose it as `newline` with `alias($._NL, $.newline)`.
- Keep structural-delimiter contexts unchanged for now.

Initial target contexts:

1. `_paragraph_line`
2. `_verse_line`
3. any multiline inline text contexts needed by semantic reconstruction (`_link_description`, `_fn_ref_def`) if required

Result: semantic constructors get explicit line boundaries where they matter for text assembly, without adding noise across the entire tree.

### Phase 2: Expose blank lines in section-like bodies

Introduce visible `blank_line` nodes where body reconstruction needs separators.

Approach:

- keep `_blank_line` token definition
- use aliases in sequence containers, for example:
  - `section`
  - `zeroth_section`
  - block/drawer bodies where semantic reconstruction needs separation semantics

This yields explicit body streams: `element, blank_line, element...`.

### Phase 3: Expose indentation fields using existing `_INDENT`

Add `field('indent', alias($._INDENT, $.indent))` to section-level elements that can be indented, prioritizing:

1. `paragraph`
2. `plain_list` / `_indented_plain_list` boundary contexts
3. drawers and blocks (`drawer`, `logbook_drawer`, greater/lesser blocks)
4. fixed-width and other line-based elements where indent affects nesting semantics

Guidelines:

- Prefer existing regex `_INDENT` over introducing scanner complexity.
- Keep `item_indent` as-is for list items.
- Preserve behavior where indent is optional and can be zero; semantic layer can normalize missing indent to column 0.

### Phase 4: Semantic reconstruction implementation

In Python semantic node construction:

1. reconstruct text objects from inline nodes plus explicit `newline` nodes
2. reconstruct section body as ordered stream of `element | blank_line`
3. recover nesting using indent fields (`item_indent` + `indent`)
4. keep raw-node access for debugging and compatibility checks

### Phase 5: Re-evaluate parser-side continuation complexity

Only after phases 1-4 pass:

- evaluate whether `_PARAGRAPH_CONTINUE` can be simplified
- do not remove it unless corpus tests and downstream semantic behavior remain equivalent

---

## Why this revised plan is safer

- It addresses the core concern (newlines and blank lines visible to semantics).
- It avoids immediate grammar-wide tree noise.
- It limits scanner risk by reusing `_INDENT` first.
- It keeps parser disambiguation stable while semantic logic is built.

---

## Testing strategy

For each phase:

1. Regenerate parser artifacts (`npm run generate` in `tree-sitter-org/`).
2. Run `tree-sitter test` and review only expected deltas.
3. Rebuild `org.so` (`tree-sitter build`).
4. Run Python quality gate (`poetry run task check`).
5. Add focused regression tests in:
   - `tree-sitter-org/test/corpus/` for grammar shape
   - `tests/` for semantic reconstruction behavior

Recommended new regression cases:

- multiline paragraph with inline markup crossing line boundaries
- section with alternating elements and blank lines
- mixed-indentation blocks under heading sections
- nested-list reconstruction from flat `plain_list` + indent fields

---

## Open decisions

1. Exact scope of `newline` aliases in phase 1 (paragraph/verse only vs also multiline inline-object contexts).
2. Exact scope of `blank_line` aliases (all section-like containers vs selected containers first).
3. Whether semantic layer should store indent as raw whitespace, normalized column, or both.
4. Threshold for considering `_PARAGRAPH_CONTINUE` simplification safe.

---

## Deliverables

1. Grammar updates with targeted `newline` and `blank_line` visibility.
2. Incremental indent field exposure using `_INDENT`.
3. Semantic reconstruction updates for text and body streams.
4. Passing corpus + Python test suites.
5. Short architecture note documenting the final contract between parser output and semantic reconstruction.
