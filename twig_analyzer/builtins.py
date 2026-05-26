"""Built-in Twig 3.x definitions: tags, filters, functions, tests.

Data is loaded from YAML files in twig_analyzer/data/ at import time.
To add custom definitions, edit the YAML files or use .twig-analyzer.yml.

Based on https://twig.symfony.com/doc/3.x/ documentation.
"""

from __future__ import annotations

# Re-export everything from the data loader (YAML-backed)
from twig_analyzer.data import (
    BUILTIN_TAGS,
    BUILTIN_FILTERS,
    BUILTIN_FUNCTIONS,
    BUILTIN_TESTS,
    BLOCK_TAGS,
    END_TAG_MAP,
    CONDITIONAL_TAGS,
    GLOBAL_VARIABLES,
    DEPRECATED,
)
