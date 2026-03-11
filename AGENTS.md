# AGENTS.md
Guidance for coding agents in `org-mode-parser`.

## Repository Map

### Tree-sitter grammar package (`tree-sitter-org/`)
- Grammar source: `tree-sitter-org/grammar.js`
- External scanner source: `tree-sitter-org/src/scanner.c`
- Syntax highlighting query: `tree-sitter-org/queries/highlights.scm`
- Corpus tests: `tree-sitter-org/test/corpus/*.txt`
- Example fixtures: `examples/*.org`
- Parse helper scripts: `check.py`, `leaf_errors.py`

### Python library (`src/`, `tests/`)
- Package root: `src/org_parser/`
- Language/parser singleton: `src/org_parser/_lang.py`
- Document parsing: `src/org_parser/document/` — exposes `load_raw()`
- Element stubs: `src/org_parser/element/`
- Text/markup stubs: `src/org_parser/text/`
- Test suite: `tests/`
- Project config (Poetry, ruff, mypy, pytest): `pyproject.toml`
- Pyright LSP config: `pyrightconfig.json`

## Toolchain (CI-aligned)
- Node.js: `20`
- Python: `3.12`
- Tree-sitter CLI: `0.26.6`
- Poetry: `2.3.2`

## Setup

### Tree-sitter grammar
Run inside `tree-sitter-org/`:
```bash
npm install
npm run generate   # only when parser artifacts need regeneration
```

### Python library
Run from the repository root:
```bash
poetry install
```

## Build Commands

### Tree-sitter grammar
From `tree-sitter-org/`:
```bash
npm run build       # tree-sitter generate && node-gyp build
tree-sitter generate
node-gyp build
tree-sitter build   # compile org.so (required by the Python library)
tree-sitter parse ../examples/simple.org
```

`org.so` (the shared library loaded by the Python library) is produced by
`tree-sitter build`. It is **gitignored** and must be rebuilt whenever
`grammar.js` or `scanner.c` changes.

## Test Commands

### Tree-sitter grammar
From `tree-sitter-org/`:
```bash
npm test
# or: tree-sitter test
tree-sitter test --file-name test/corpus/headings.txt
tree-sitter test --file-name test/corpus/headings.txt --include "Level 1 heading"
tree-sitter test --exclude "TODO"
tree-sitter test --update   # intentional expected-tree updates only
```

### Python library
From the repository root, use taskipy tasks via Poetry:
```bash
poetry run task check         # full quality gate: format · lint · types · tests
poetry run task test          # pytest with branch coverage
poetry run task lint          # ruff lint check
poetry run task lint-fix      # ruff lint with auto-fix
poetry run task format-check  # verify ruff formatting (dry-run)
poetry run task format        # apply ruff formatting
poetry run task type          # mypy strict type check
```

## Parse-Check Commands
From repo root:
```bash
python3 check.py "examples/*.org" "*.org"
python3 check.py examples/simple.org
python3 leaf_errors.py examples/simple.org --context 2
```

## Linting / Formatting

### Tree-sitter grammar
No dedicated lint config. Preserve existing style in touched files.

### Python library
All configuration lives in `pyproject.toml`. The full quality gate is:
```bash
poetry run task check
```

Tool responsibilities:
- **ruff** — formatting (replaces black) and linting (replaces flake8/isort).
  Selected rule groups: `E W F I N D UP ANN B C4 SIM TCH PERF RUF PL`.
- **mypy** — strict static type checking (`strict = true`).
- **pyright** — editor LSP server; `typeCheckingMode = "strict"` in
  `pyrightconfig.json`.
- **pytest** — test runner with branch coverage via `pytest-cov`.

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

## Code Style: Python scripts (`check.py`, `leaf_errors.py`)
- PEP8-like formatting with 4-space indentation.
- Keep imports tidy and stdlib-first (currently stdlib-only).
- Prefer `Path` for filesystem paths.
- Use precise type hints (`list[str]`, `tuple[...]`, `Path`).
- Use `@dataclass` for structured results.
- Return exit codes from `main()` and call `SystemExit(main())`.
- Send usage/errors to `stderr`.

## Code Style: Python library (`src/org_parser/`)
- `from __future__ import annotations` at the top of every module.
- 88-character line length (ruff default).
- Google-style docstrings on all public and private functions, classes, and
  modules. Docstrings are enforced by ruff's `D` rule group.
- Type annotations are required on every function signature (ruff `ANN`
  rules). Use `TYPE_CHECKING` guards for imports used only in annotations.
- Runtime imports that are only referenced in type annotations must be moved
  into `if TYPE_CHECKING:` blocks (ruff `TCH` rule).
- `__all__` must be defined on every public module.
- Internal modules and helpers use a leading underscore (e.g., `_lang.py`,
  `_loader.py`).
- Avoid `Any` except where unavoidable for ctypes interop (ruff `ANN401` is
  ignored for this reason).
- `no_implicit_reexport = true` in mypy: symbols must be explicitly listed in
  `__all__` or re-exported with `import X as X` to be part of the public API.

## Naming Conventions
- Grammar and AST node names: `snake_case`.
- Scanner helpers: lower snake, verb-oriented (`scan_*`, `is_*`, `extract_*`).
- Python functions: lower snake case.
- Python classes/dataclasses: PascalCase.
- Python internal modules/helpers: leading underscore prefix.
- Prefer domain terms over generic names.

## Error Handling Expectations
- Favor resilient parsing and recovery over hard-fail behavior.
- Preserve existing recovery semantics unless intentionally improving them.
- For scripts, handle missing tools/files with actionable diagnostics.
- Avoid uncaught exceptions for common user input errors.
- In the Python library, raise `FileNotFoundError` (not a custom type) for
  missing files; let tree-sitter errors propagate unchanged.

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
- For Python library changes, run `poetry run task check` before finishing.

## Pre-Completion Checklist

### Grammar / scanner changes
- If you changed `grammar.js` or `src/scanner.c`, rebuild parser artifacts:
  `npm run build` (inside `tree-sitter-org/`) and `tree-sitter build` (to
  refresh `org.so` for the Python library).
- Run full `tree-sitter test` before final handoff.
- Run `python3 check.py "examples/*.org" "*.org"` from repo root.
- Ensure no generated-file edits were made manually.
- Keep commit scope focused on one syntax concern where possible.

### Python library changes
- Run `poetry run task check` from the repository root. All four stages must
  pass: `format-check`, `lint`, `type`, `test`.
- If `grammar.js` or `scanner.c` was also changed, rebuild `org.so` first
  (`tree-sitter build` inside `tree-sitter-org/`) before running Python tests.
- Ensure no changes to generated files were made manually.
