"""Configuration file discovery and loading for twig-analyzer.

Looks for .twig-analyzer.yml (or .twig-analyzer.yaml) by walking up
from the template file's directory. Supports project-wide declarations
so you don't need {# @var #} annotations in every template.

Schema:
    globals:        [app, user, items]         # variables always in scope
    filters:        [my_filter, custom_filter]  # custom Twig filters
    functions:      [my_func, custom_func]      # custom Twig functions
    tests:          [is_valid, instanceof]      # custom Twig tests
    tags:           [my_tag, form_theme]        # custom Twig tags
"""

from __future__ import annotations
import os
from dataclasses import dataclass, field, replace
from typing import Dict, FrozenSet, List, Optional, Set, Tuple
from pathlib import Path


@dataclass(frozen=True)
class TwigAnalyzerConfig:
    """Immutable analyzer configuration loaded from YAML file."""

    globals: FrozenSet[str] = frozenset()
    filters: FrozenSet[str] = frozenset()
    functions: FrozenSet[str] = frozenset()
    tests: FrozenSet[str] = frozenset()
    tags: FrozenSet[str] = frozenset()

    # Path to the config file that was loaded (for diagnostics)
    config_path: str = ""

    # ═══════════════════════════════════════════════════════════════════
    # Factory: load from raw dict
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def from_dict(data: dict, config_path: str = "") -> TwigAnalyzerConfig:
        """Create config from a plain dictionary (parsed YAML).

        Only known keys are accepted; unknown keys are silently ignored.
        All values should be lists of strings.
        """
        return TwigAnalyzerConfig(
            globals=frozenset(_to_str_list(data.get("globals", []))),
            filters=frozenset(_to_str_list(data.get("filters", []))),
            functions=frozenset(_to_str_list(data.get("functions", []))),
            tests=frozenset(_to_str_list(data.get("tests", []))),
            tags=frozenset(_to_str_list(data.get("tags", []))),
            config_path=config_path,
        )

    @staticmethod
    def empty() -> TwigAnalyzerConfig:
        """Return an empty config (no custom declarations)."""
        return TwigAnalyzerConfig()

    def is_empty(self) -> bool:
        """True if no declarations are configured."""
        return not (self.globals or self.filters or self.functions or self.tests or self.tags)

    def to_annotations(self) -> str:
        """Generate synthetic {# @kind name #} comment lines for all declarations.

        These are prepended to the source before parsing so all rules
        see them without needing signature changes.
        """
        lines: List[str] = []
        for name in sorted(self.globals):
            lines.append(f"{{# @var {name} #}}")
        for name in sorted(self.filters):
            lines.append(f"{{# @filter {name} #}}")
        for name in sorted(self.functions):
            lines.append(f"{{# @function {name} #}}")
        for name in sorted(self.tests):
            lines.append(f"{{# @test {name} #}}")
        for name in sorted(self.tags):
            lines.append(f"{{# @tag {name} #}}")
        return "\n".join(lines)

    # ═══════════════════════════════════════════════════════════════════
    # Merge: combine two configs (project + template-local)
    # ═══════════════════════════════════════════════════════════════════

    def merge(self, other: TwigAnalyzerConfig) -> TwigAnalyzerConfig:
        """Combine two configs, taking the union of all sets."""
        return TwigAnalyzerConfig(
            globals=self.globals | other.globals,
            filters=self.filters | other.filters,
            functions=self.functions | other.functions,
            tests=self.tests | other.tests,
            tags=self.tags | other.tags,
            config_path=self.config_path or other.config_path,
        )

    # ═══════════════════════════════════════════════════════════════════
    # Discovery: walk up directories to find config file
    # ═══════════════════════════════════════════════════════════════════

    CONFIG_FILENAMES: Tuple[str, ...] = (
        ".twig-analyzer.yml",
        ".twig-analyzer.yaml",
        ".twiganalyzer.yml",
    )

    @staticmethod
    def discover(start_dir: str) -> TwigAnalyzerConfig:
        """Walk up from start_dir to find a config file.

        Returns the merged config from all found files, with deeper
        directories taking precedence (last wins for conflicts).
        """
        configs: List[TwigAnalyzerConfig] = []
        current = Path(start_dir).resolve()

        # Walk up to filesystem root
        for directory in [current] + list(current.parents):
            for fname in TwigAnalyzerConfig.CONFIG_FILENAMES:
                candidate = directory / fname
                if candidate.is_file():
                    try:
                        cfg = TwigAnalyzerConfig._load_file(str(candidate))
                        configs.append(cfg)
                    except Exception:
                        pass  # Skip unparseable configs
                    break  # Only load one config per directory

        # Merge all found configs (closest to file takes precedence)
        result = TwigAnalyzerConfig.empty()
        for cfg in configs:
            result = result.merge(cfg)
        return result

    # ═══════════════════════════════════════════════════════════════════
    # Internal: load and parse a single YAML file
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _load_file(path: str) -> TwigAnalyzerConfig:
        """Parse a single .twig-analyzer.yml file."""
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return TwigAnalyzerConfig.empty()
        return TwigAnalyzerConfig.from_dict(data, config_path=path)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _to_str_list(value) -> List[str]:
    """Normalize a YAML value to a list of strings."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []
