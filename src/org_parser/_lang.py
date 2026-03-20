"""Internal: tree-sitter Language and Parser singletons for Org Mode.

This module loads the compiled ``org.so`` shared library and exposes a
module-level :data:`ORG_LANGUAGE` and a ready-to-use :data:`PARSER` instance.
Both are initialised once at import time and shared across the process.

The shared library is located via the following lookup strategy (in order):

1. The ``ORG_PARSER_LIB`` environment variable, if set, is treated as an
   absolute path to ``org.so``.
2. A path relative to the repository root:
   ``<repo_root>/tree-sitter-org/org.so`` where *repo_root* is two levels
   above this file (``src/org_parser/_lang.py`` → ``src/org_parser`` →
   ``src`` → repo root).

Implementation note on language loading
----------------------------------------
The grammar is compiled without auto-generated Python bindings, so the
``tree_sitter_org`` symbol is loaded via :mod:`ctypes`. tree-sitter 0.24+
expects a ``PyCapsule`` object (named ``"tree_sitter.Language"``) rather than
a raw integer pointer; we construct one manually using the CPython
``PyCapsule_New`` C API to avoid the deprecation path.
"""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

import tree_sitter

__all__ = ["ORG_LANGUAGE", "PARSER"]


def _find_lib() -> Path:
    """Return the path to the compiled ``org.so`` shared library.

    Raises:
        FileNotFoundError: If the library cannot be found at any of the
            expected locations.
    """
    env_value = os.environ.get("ORG_PARSER_LIB")
    if env_value:
        candidate = Path(env_value)
        if not candidate.exists():
            raise FileNotFoundError(
                f"ORG_PARSER_LIB is set to {env_value!r} but no file exists "
                "at that path."
            )
        return candidate

    # Walk up: src/org_parser/_lang.py -> src/org_parser -> src -> repo root
    repo_root = Path(__file__).parent.parent.parent
    candidate = repo_root / "tree-sitter-org" / "org.so"
    if candidate.exists():
        return candidate

    raise FileNotFoundError(
        "Cannot locate the org-mode shared library (org.so). "
        f"Expected it at: {candidate!s}. "
        "Set the ORG_PARSER_LIB environment variable to the absolute path "
        "of the compiled shared library to override the default lookup."
    )


def _make_capsule(ptr: int) -> object:
    """Wrap a raw C pointer in a ``PyCapsule`` named ``"tree_sitter.Language"``.

    tree-sitter 0.24+ expects a capsule object rather than a plain integer
    when constructing a :class:`~tree_sitter.Language`.  We create one via the
    CPython C API exposed through :mod:`ctypes`.

    Args:
        ptr: The raw pointer value returned by ``tree_sitter_org()``.

    Returns:
        A Python capsule object usable as the argument to
        :class:`tree_sitter.Language`.
    """
    pythonapi = ctypes.pythonapi
    pythonapi.PyCapsule_New.restype = ctypes.py_object
    pythonapi.PyCapsule_New.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
    ]
    return pythonapi.PyCapsule_New(ptr, b"tree_sitter.Language", None)


def _load_language() -> tree_sitter.Language:
    """Load and return the Org Mode tree-sitter :class:`~tree_sitter.Language`.

    Uses :mod:`ctypes` to open the shared library, resolves the
    ``tree_sitter_org`` symbol, wraps the resulting pointer in a
    ``PyCapsule``, and passes it to :class:`~tree_sitter.Language`.

    Returns:
        An initialised :class:`~tree_sitter.Language` for Org Mode.

    Raises:
        FileNotFoundError: If the shared library cannot be found.
        OSError: If the shared library cannot be loaded by the dynamic linker.
        AttributeError: If ``tree_sitter_org`` symbol is not exported by the
            library.
    """
    lib_path = _find_lib()
    lib = ctypes.CDLL(str(lib_path))
    lib.tree_sitter_org.restype = ctypes.c_void_p
    raw_ptr: int = lib.tree_sitter_org()
    capsule = _make_capsule(raw_ptr)
    return tree_sitter.Language(capsule)


#: The Org Mode :class:`~tree_sitter.Language` instance (module-level singleton).
ORG_LANGUAGE: tree_sitter.Language = _load_language()

#: A :class:`~tree_sitter.Parser` pre-configured with :data:`ORG_LANGUAGE`.
PARSER: tree_sitter.Parser = tree_sitter.Parser(ORG_LANGUAGE)
