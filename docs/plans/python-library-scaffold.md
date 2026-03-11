# Python Library Scaffold

**Status:** In progress  
**Date:** 2026-03-07

## Goal

Bootstrap a Poetry-managed Python package (`org-parser`) that exposes the
tree-sitter org-mode parser through thin Python bindings. The initial surface
is intentionally minimal: a single `org_parser.document.load_raw()` function
that parses an `.org` file and returns the raw `tree_sitter.Tree` object.
User-facing ergonomics will be addressed in follow-up work.

---

## Project Layout

```
pyproject.toml              # Poetry project + all tool configuration
pyrightconfig.json          # Pyright LSP configuration (strict)
src/
  org_parser/
    __init__.py             # Package root; re-exports top-level public API
    py.typed                # PEP 561 marker — signals full type annotation
    _lang.py                # Internal: language/parser singleton
    document/
      __init__.py           # Re-exports load_raw()
      _loader.py            # load_raw() implementation
    element/
      __init__.py           # Placeholder — greater & lesser elements (future)
    text/
      __init__.py           # Placeholder — rich text objects (future)
tests/
  __init__.py
  conftest.py               # Shared fixtures (examples_dir, sample paths)
  test_document.py          # Tests for load_raw()
docs/
  plans/
    python-library-scaffold.md   # This file
```

---

## Toolchain

| Tool | Role | Strictness |
|---|---|---|
| **Poetry 2.x** | Build, dependency, and virtual-env management | — |
| **ruff** | Linting + formatting (replaces flake8, isort, black) | Full ruleset, error on any violation |
| **mypy** | Static type-checking | `strict = true` |
| **pyright** | LSP type server for editor integration | `typeCheckingMode = "strict"` |
| **pytest** | Test runner | `--strict-markers`, `--tb=short` |
| **pytest-cov** | Coverage reporting | Branch coverage tracked |

---

## Dependencies

### Runtime

| Package | Version constraint | Purpose |
|---|---|---|
| `tree-sitter` | `^0.23` | Python bindings for the tree-sitter parsing library |

### Development

| Package | Version constraint | Purpose |
|---|---|---|
| `mypy` | `^1.11` | Static type checking |
| `ruff` | `^0.8` | Linting and formatting |
| `pytest` | `^8.3` | Test runner |
| `pytest-cov` | `^6.0` | Coverage reporting |
| `pyright` | `^1.1` | Editor LSP server (strict type checking) |

---

## Loading the Shared Library

The compiled grammar lives at `tree-sitter-org/org.so` (C shared library
exporting `tree_sitter_org(void) -> TSLanguage *`).

No auto-generated Python bindings (`bindings/python/`) exist yet, so the
library is loaded via `ctypes`:

```python
import ctypes
import os
from pathlib import Path

from tree_sitter import Language, Parser

def _find_lib() -> Path:
    env = os.environ.get("ORG_PARSER_LIB")
    if env:
        return Path(env)
    # Walk up from src/org_parser/ to repo root
    repo_root = Path(__file__).parent.parent.parent
    candidate = repo_root / "tree-sitter-org" / "org.so"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(
        "Cannot locate org.so. Set the ORG_PARSER_LIB environment variable "
        "to the absolute path of the compiled shared library."
    )

def _make_language() -> Language:
    lib_path = _find_lib()
    lib = ctypes.CDLL(str(lib_path))
    lib.tree_sitter_org.restype = ctypes.c_void_p
    return Language(lib.tree_sitter_org())

ORG_LANGUAGE: Language = _make_language()
_PARSER: Parser = Parser(ORG_LANGUAGE)
```

This approach avoids any build step on the Python side and works with the
pre-compiled artifact already in the repository. The `ORG_PARSER_LIB`
environment variable provides an escape hatch for non-standard setups.

### Future: proper Python bindings

Once Python bindings are generated (`tree-sitter generate --lang python`) or a
standalone `tree-sitter-org` PyPI package exists, `_lang.py` can be replaced
with a direct import (`import tree_sitter_org`), removing the ctypes layer
entirely.

---

## `load_raw()` Signature

```python
from pathlib import Path
import tree_sitter

def load_raw(path: str | Path) -> tree_sitter.Tree:
    """Parse an org file and return the raw tree-sitter parse tree.

    Args:
        path: Absolute or relative path to the .org file.

    Returns:
        A ``tree_sitter.Tree`` whose root node has type ``document``.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        OSError: If the file cannot be read.
    """
```

The `Tree` object exposes:
- `tree.root_node` — root `Node` of type `document`
- `node.children` — child nodes
- `node.type` — grammar rule name (e.g. `"heading"`, `"section"`)
- `node.start_point`, `node.end_point` — `(line, column)` tuples
- `node.text` — raw bytes for the node span
- `parser.walk()` / cursor API — efficient tree traversal

---

## Test Strategy

`tests/conftest.py` provides:
- `examples_dir: Path` — fixture pointing to `examples/`
- Helper to read example files

`tests/test_document.py` covers:
- `simple.org` — successful parse, no ERROR nodes in root
- `empty.org` — valid tree returned for empty input
- `large.org` — root node type is `"document"`, tree has children
- Missing file — `FileNotFoundError` is raised

---

## Tool Configuration Notes

### ruff

Selected rule groups:

| Code | Group | Rationale |
|---|---|---|
| `E`, `W` | pycodestyle | Style baseline |
| `F` | pyflakes | Undefined names, unused imports |
| `I` | isort | Import ordering |
| `N` | pep8-naming | Naming conventions |
| `D` | pydocstring | Docstring presence and formatting |
| `UP` | pyupgrade | Modern Python idioms |
| `ANN` | flake8-annotations | Type annotation coverage |
| `B` | flake8-bugbear | Likely bugs |
| `C4` | flake8-comprehensions | Idiomatic comprehensions |
| `SIM` | flake8-simplify | Code simplification |
| `TCH` | flake8-type-checking | `TYPE_CHECKING` guard discipline |
| `PERF` | Perflint | Performance anti-patterns |
| `RUF` | ruff-specific | Ruff's own rules |
| `PT` | flake8-pytest-style | Pytest best practices (tests only) |
| `PL` | Pylint | High-signal pylint rules |

### mypy

`strict = true` enables: `disallow_untyped_defs`, `disallow_incomplete_defs`,
`check_untyped_defs`, `disallow_any_generics`, `disallow_untyped_decorators`,
`warn_redundant_casts`, `warn_unused_ignores`, `warn_return_any`,
`no_implicit_reexport`, `strict_equality`.

`tree_sitter` stubs are incomplete; `ignore_missing_imports = true` is set for
that module only.

### pyright

`typeCheckingMode = "strict"` adds: `reportMissingImports`,
`reportMissingTypeStubs`, `reportUnknownMemberType`, etc.

---

## Out of Scope (This Plan)

- Auto-generating Python bindings from `grammar.js`
- High-level document model (headings, sections, properties as Python objects)
- Packaging/distribution to PyPI
- Performance benchmarks
- Type stubs for `tree-sitter`
