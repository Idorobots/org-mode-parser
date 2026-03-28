# AGENTS.md
Guidance for coding agents working in `org-mode-parser`.

## Scope and Structure
- Monorepo with two primary parts:
  - Tree-sitter grammar package: `tree-sitter-org/`
  - Python wrapper library: `src/org_parser/`, tests in `tests/`
- Root helpers:
  - Parse checks: `check.py`, `leaf_errors.py`
  - Project config: `pyproject.toml`, `pyrightconfig.json`

## Repository Map
- Grammar source: `tree-sitter-org/grammar.js`
- External scanner: `tree-sitter-org/src/scanner.c`
- Tree-sitter corpus tests: `tree-sitter-org/test/corpus/*.txt`
- Tree-sitter query files: `tree-sitter-org/queries/*.scm`
- Python package root: `src/org_parser/`
- Document loader API: `src/org_parser/document/` (exposes `load_raw()`)
- Examples/fixtures: `examples/*.org`
- Python tests: `tests/*.py`

## Toolchain (CI-Aligned)
- Node.js: `20`
- Python: `3.12`
- Tree-sitter CLI: `0.26.x`
- Poetry: `2.3.x`
- Python QA stack: `ruff`, `mypy`, `pytest`, `pytest-cov`, `pyright`

## Setup
### Tree-sitter grammar setup (run inside `tree-sitter-org/`)
```bash
npm install
npm run generate
```

### Python setup (run from repo root)
```bash
poetry install
```

## Build Commands
### Tree-sitter grammar (`tree-sitter-org/`)
```bash
npm run build          # tree-sitter generate && tree-sitter build
npm run generate       # regenerate parser artifacts only
tree-sitter build      # produces tree-sitter-org/org.so
npm run parse -- ../examples/simple.org
```

Notes:
- `org.so` is required by the Python package at runtime.
- Rebuild `org.so` after edits to `grammar.js` or `src/scanner.c`.

## Lint / Type / Test Commands
### Tree-sitter grammar (`tree-sitter-org/`)
```bash
npm test
tree-sitter test
tree-sitter test --file-name test/corpus/headings.txt
tree-sitter test --file-name test/corpus/headings.txt --include "Level 1 heading"
tree-sitter test --exclude "TODO"
tree-sitter test --update   # only when intentionally updating expected trees
```

### Python library (repo root)
Use taskipy tasks from `pyproject.toml`:
```bash
poetry run task format-check
poetry run task lint
poetry run task type
poetry run task test
poetry run task check        # format-check + lint + type + test
poetry run task lint-fix
poetry run task format
```

### Running a single Python test (important)
```bash
poetry run pytest tests/test_document.py::TestLoadRaw::test_simple_org_returns_tree -q
poetry run pytest tests/test_document.py::TestLoadRaw -q
poetry run pytest tests/test_document.py -q
poetry run pytest -k "simple_org and not recovery" -q
```

## Parse-Check Utilities (repo root)
```bash
python3 check.py "examples/*.org" "*.org"
python3 check.py examples/simple.org
python3 leaf_errors.py examples/simple.org --context 2
```
- `check.py` can be slow; allow extended timeout (~300s).

## Fuzz Sanity Checks
Use fuzzing when parser edits touch incremental parsing behavior or recovery.

### `tree-sitter fuzz` quick pass (`tree-sitter-org/`)
```bash
tree-sitter fuzz --iterations 10 --edits 3
```
- Mutates corpus inputs and compares incremental parse behavior against full reparse behavior.
- Use `--include` / `--exclude` to target a corpus test title subset.

### Capture replayable failing snapshots
```bash
tree-sitter fuzz --log-graphs --iterations 50 --edits 5 --include "heading"
```
- `--log-graphs` prints per-edit input snapshots to stdout.
- If fuzz reports an incorrect parse, copy the logged block for replay.

### Replay with `fuzz.py` (repo root)
```bash
# Paste a single fuzz log block into fuzz_input.log first
python3 fuzz.py < fuzz_input.log
python3 fuzz.py --lib-path tree-sitter-org/org.so < fuzz_input.log
```
- `fuzz.py` parses snapshot logs, computes contiguous edits, replays incremental parsing, and compares S-expressions against full parses at each step.
- Exit code `0` means all steps matched, `1` means mismatch detected, `2` means malformed input/usage error.

## Generated Files (Do Not Hand-Edit nor read)
- `tree-sitter-org/src/parser.c`
- `tree-sitter-org/src/grammar.json`
- `tree-sitter-org/src/node-types.json`
- `tree-sitter-org/src/tree_sitter/*`
- `tree-sitter-org/org.so`
- `tree-sitter-org/tree-sitter-org.wasm`

Regenerate generated artifacts with `npm run build` or `npm run generate`.

## Code Style and Conventions
### General
- Keep diffs focused; avoid unrelated refactors.
- Follow existing naming and module boundaries.
- Preserve parser recovery behavior unless intentionally improving it.

### `grammar.js` style (`tree-sitter-org/grammar.js`)
- 2-space indentation.
- Semicolons required.
- Prefer single-quoted strings.
- Keep helpers small and near top-level.
- Use comments only for non-obvious scanner/grammar interactions.
- Public rules: `snake_case` (e.g., `plain_list`).
- Internal rules: leading underscore (e.g., `_object`, `_NL`).
- Token-like internals may use upper snake (`_TODO_KW`, `_PLAN_KW`).
- Use `field(...)` for meaningful named children.
- Use `prec(...)` only where ambiguity needs it.

### Scanner style (`tree-sitter-org/src/scanner.c`)
- Keep token enum order aligned with `externals` in `grammar.js`.
- Prefer `static` helpers and `bool` predicates.
- Use fixed-width integer state (`uint8_t`, `uint16_t`, `int32_t`).
- Constants/macros in `UPPER_SNAKE_CASE`.
- Preserve bounds/serialization guards (`MAX_*`, `SERIALIZE_BUF_SIZE`).
- Avoid dynamic allocation unless truly necessary.
- Document subtle state-machine invariants where needed.

### Python style (`src/org_parser/`, `tests/`)
- `from __future__ import annotations` at top of each module.
- Ruff formatting rules apply; line length is `88`.
- Quote style is double quotes (ruff formatter).
- Google-style docstrings are required in library modules.
- Type annotations required for library function signatures.
- Use `TYPE_CHECKING` imports for type-only dependencies.
- Keep imports sorted (ruff/isort behavior).
- Define `__all__` in public modules.
- Internal modules/helpers should use leading underscore.
- Prefer precise types (`Path`, `list[str]`, `tuple[...]`).
- Avoid `Any` unless unavoidable (ctypes interop is an accepted exception).

### Naming
- Grammar/AST node names: `snake_case`
- Scanner helpers: verb-oriented lower snake (`scan_*`, `is_*`)
- Python functions/variables: `snake_case`
- Python classes/dataclasses: `PascalCase`
- Prefer domain-specific names over generic placeholders

### Error handling
- Prefer resilient parsing and recovery over hard-fail behavior.
- Python file loading should raise `FileNotFoundError` for missing paths.
- Let tree-sitter parse/loader errors propagate unless there is a clear recovery path.
- Script diagnostics should be actionable and directed to stderr when appropriate.

## Agent Workflow
- Read nearby grammar/scanner/library code before editing.
- Run the narrowest relevant test first (single file/test/title), then broaden.
- For grammar/scanner changes:
  - Rebuild: `npm run build` (in `tree-sitter-org/`)
  - Run grammar tests: `tree-sitter test`
  - Run parse checks: `python3 check.py "examples/*.org" "*.org"`
- For Python library changes:
  - Run: `poetry run task check`
  - If grammar changed, rebuild `org.so` before Python tests.
