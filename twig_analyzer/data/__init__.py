"""Data loader — reads YAML definition files into Python dicts.

All YAML files are loaded once at import time. The module exports
the same names as builtins.py so it's a drop-in replacement.

Files:
    data/tags.yml       → BUILTIN_TAGS, BLOCK_TAGS, END_TAG_MAP
    data/filters.yml    → BUILTIN_FILTERS
    data/functions.yml  → BUILTIN_FUNCTIONS
    data/tests.yml      → BUILTIN_TESTS
    data/globals.yml    → GLOBAL_VARIABLES, DEPRECATED, CONDITIONAL_TAGS
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, FrozenSet, Set

import yaml

_DATA_DIR = Path(__file__).parent


def _load_yaml(name: str) -> dict:
    """Load a YAML file from the data directory. Returns {} if not found."""
    path = _DATA_DIR / f"{name}.yml"
    if not path.is_file():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ═══════════════════════════════════════════════════════════════════════
# 1. Tags
# ═══════════════════════════════════════════════════════════════════════

_tags_raw = _load_yaml("tags")

BUILTIN_TAGS: Dict[str, dict] = {
    name: {
        "block": info.get("block", False),
        "description": info.get("description", ""),
        "since": str(info.get("since", "—")),
        "example": info.get("example", ""),
    }
    for name, info in _tags_raw.items()
}

# Derived: tags that require matching end tags
BLOCK_TAGS: Set[str] = {tag for tag, info in BUILTIN_TAGS.items() if info["block"]}

# Derived: end-tag mapping (automatic: block → endblock)
END_TAG_MAP: Dict[str, str] = {
    tag: f"end{tag}"
    for tag in BLOCK_TAGS
}

# ═══════════════════════════════════════════════════════════════════════
# 2. Filters
# ═══════════════════════════════════════════════════════════════════════

_filters_raw = _load_yaml("filters")

BUILTIN_FILTERS: Dict[str, dict] = {
    name: {
        "args": int(info.get("args", 0)),
        "since": str(info.get("since", "—")),
    }
    for name, info in _filters_raw.items()
}

# ═══════════════════════════════════════════════════════════════════════
# 3. Functions
# ═══════════════════════════════════════════════════════════════════════

_functions_raw = _load_yaml("functions")

BUILTIN_FUNCTIONS: Dict[str, dict] = {
    name: {
        "args": int(info.get("args", 0)),
        "since": str(info.get("since", "—")),
    }
    for name, info in _functions_raw.items()
}

# ═══════════════════════════════════════════════════════════════════════
# 4. Tests
# ═══════════════════════════════════════════════════════════════════════

_tests_raw = _load_yaml("tests")

BUILTIN_TESTS: Dict[str, dict] = {
    name: {
        "args": int(info.get("args", 0)),
        "since": str(info.get("since", "—")),
    }
    for name, info in _tests_raw.items()
}

# ═══════════════════════════════════════════════════════════════════════
# 5. Globals & Deprecated
# ═══════════════════════════════════════════════════════════════════════

_globals_raw = _load_yaml("globals")

GLOBAL_VARIABLES: FrozenSet[str] = frozenset(
    str(v) for v in _globals_raw.get("global_variables", [])
)

CONDITIONAL_TAGS: Set[str] = set(
    str(t) for t in _globals_raw.get("conditional_tags", [])
)

DEPRECATED: Dict[str, dict] = {
    name: {
        "type": str(info.get("type", "")),
        "since": str(info.get("since", "")),
        "message": str(info.get("message", "")),
        "removed_in": str(info.get("removed_in", "")),
    }
    for name, info in _globals_raw.get("deprecated", {}).items()
}
