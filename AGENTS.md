# AGENTS.md
Guidance for coding agents in `org-mode-parser`.

## Repository Map
- Main parser package: `tree-sitter-org/`
- Grammar source: `tree-sitter-org/grammar.js`
- External scanner source: `tree-sitter-org/src/scanner.c`
- Syntax highlighting query: `tree-sitter-org/queries/highlights.scm`
- Corpus tests: `tree-sitter-org/test/corpus/*.txt`
- Example fixtures: `examples/*.org`
- Parse helper scripts: `check.py`, `leaf_errors.py`

## Toolchain (CI-aligned)
- Node.js: `20`
- Python: `3.12`
- Tree-sitter CLI: `0.26.6`

## Setup
Run inside `tree-sitter-org/`:
```bash
npm install
npm run generate   # only when parser artifacts need regeneration
```

## Build Commands
From `tree-sitter-org/`:
```bash
npm run build
tree-sitter generate
node-gyp build
tree-sitter parse ../examples/simple.org
```

## Test Commands
From `tree-sitter-org/`.
```bash
npm test
# or: tree-sitter test
tree-sitter test --file-name test/corpus/headings.txt
tree-sitter test --file-name test/corpus/headings.txt --include "Level 1 heading"
tree-sitter test --exclude "TODO"
tree-sitter test --update   # intentional expected-tree updates only
```

## Parse-Check Commands
From repo root:
```bash
python3 check.py "examples/*.org" "*.org"
python3 check.py examples/simple.org
python3 leaf_errors.py examples/simple.org --context 2
```

## Linting / Formatting
- No dedicated lint config is present (no ESLint/Prettier/ruff/flake8 files detected).
- Use these quality gates before finishing:
  - `tree-sitter test`
  - `python3 check.py "examples/*.org" "*.org"`
- Preserve existing style in touched files.

## Generated Files (Do Not Hand-Edit)
- `tree-sitter-org/src/parser.c`
- `tree-sitter-org/src/grammar.json`
- `tree-sitter-org/src/node-types.json`
- `tree-sitter-org/src/tree_sitter/*`
- `tree-sitter-org/org.so`
- `tree-sitter-org/tree-sitter-org.wasm`

After grammar/scanner edits, regenerate with `npm run build` or `npm run generate`.

## Code Style: `grammar.js`
- 2-space indentation.
- Semicolons are required.
- Prefer single-quoted strings.
- Keep trailing commas in multiline literals where already used.
- Keep helper functions small and near top-level.
- Use comments only for non-obvious grammar/scanner interactions.
- Public grammar rules: `snake_case` (e.g., `plain_list`).
- Internal grammar rules: leading underscore (e.g., `_object`, `_S`, `_NL`).
- Token-like internals may use upper snake (`_TODO_KW`, `_PLAN_KW`).
- Use `field(...)` for meaningful named children.
- Use `prec(...)` only where ambiguity requires it.

## Code Style: `src/scanner.c`
- Keep external token enum order aligned with `externals` in `grammar.js`.
- Prefer `static` helpers and `bool` predicates.
- Use fixed-width integer state (`uint8_t`, `uint16_t`, `int32_t`).
- Constants/macros in `UPPER_SNAKE_CASE`.
- Preserve bounds and serialization limits (`MAX_*`, `SERIALIZE_BUF_SIZE`).
- Avoid dynamic allocation unless unavoidable.
- Document subtle lexer invariants and state transitions.

## Code Style: Python Scripts
- PEP8-like formatting with 4-space indentation.
- Keep imports tidy and stdlib-first (currently stdlib-only).
- Prefer `Path` for filesystem paths.
- Use precise type hints (`list[str]`, `tuple[...]`, `Path`).
- Use `@dataclass` for structured results.
- Return exit codes from `main()` and call `SystemExit(main())`.
- Send usage/errors to `stderr`.

## Naming Conventions
- Grammar and AST node names: `snake_case`.
- Scanner helpers: lower snake, verb-oriented (`scan_*`, `is_*`, `extract_*`).
- Python functions: lower snake case.
- Python classes/dataclasses: PascalCase.
- Prefer domain terms over generic names.

## Error Handling Expectations
- Favor resilient parsing and recovery over hard-fail behavior.
- Preserve existing recovery semantics unless intentionally improving them.
- For scripts, handle missing tools/files with actionable diagnostics.
- Avoid uncaught exceptions for common user input errors.

## Corpus Test Authoring
- Corpus file format is:
  1) `====` title block
  2) Org input
  3) `---` separator
  4) expected S-expression
- Keep test titles specific; `--include` matches these titles.
- Add focused regression tests near the affected syntax area.

## Recommended Agent Workflow
- Read nearby grammar/scanner code and relevant corpus files first.
- Run focused tests (`--file-name`, then `--include`) only when debugging issues.
- Keep diffs minimal; avoid unrelated refactors.

## Pre-Completion Checklist
- If you changed `grammar.js` or `src/scanner.c`, regenerate parser artifacts.
- Run full `tree-sitter test` before final handoff.
- Run `python3 check.py "examples/*.org" "*.org"` from repo root.
- Ensure no generated-file edits were made manually.
- Keep commit scope focused on one syntax concern where possible.
