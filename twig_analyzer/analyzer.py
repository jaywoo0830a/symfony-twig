"""Twig Static Analyzer — pure analysis pipeline.

source → parse → run rules → collect diagnostics → AnalysisResult
"""

from __future__ import annotations
from typing import Dict, Optional, Sequence

from .parser import parse, ParseError
from .diagnostics import Diagnostic, Severity, Range, AnalysisResult
from .rules import ALL_RULES, DEFAULT_SEVERITIES
from .config import TwigAnalyzerConfig


class Analyzer:
    """Core analyzer. Instantiate with optional rule config, then call .analyze().

    Usage:
        analyzer = Analyzer()
        result = analyzer.analyze(source, file_path="template.html.twig")
        lsp_diags = [d.to_lsp() for d in result.diagnostics]
    """

    def __init__(
        self,
        rules: Optional[Dict[str, bool]] = None,
        severities: Optional[Dict[str, str]] = None,
        config: Optional[TwigAnalyzerConfig] = None,
    ):
        self._enabled: Dict[str, bool] = {
            rid: rules.get(rid, True) if rules else True
            for rid in ALL_RULES
        }
        self._severities: Dict[str, Severity] = dict(DEFAULT_SEVERITIES)
        if severities:
            for rid, sev_str in severities.items():
                try:
                    self._severities[rid] = Severity[sev_str.upper()]
                except KeyError:
                    pass
        self._config = config or TwigAnalyzerConfig.empty()

    def analyze(self, source: str, file_path: str = "") -> AnalysisResult:
        """Analyze a Twig template source string. Pure: source → result.

        Config-based declarations (globals, filters, functions, tests, tags)
        are prepended as synthetic {# @kind name #} annotations so all rules
        benefit without signature changes.
        """
        result = AnalysisResult(file_path=file_path, source=source)

        # ── Inject config-based declarations as synthetic annotations ──
        augmented_source = source
        if not self._config.is_empty():
            preamble = self._config.to_annotations()
            augmented_source = preamble + "\n" + source

        # Parse
        try:
            tree = parse(augmented_source)
        except ParseError as e:
            result = result.add(Diagnostic(
                message=f"Parse error: {e}",
                severity=Severity.ERROR,
                range=Range(e.line, e.column, e.line, e.column + 1),
                rule_id="TWIG-PARSE-ERROR",
            ))
            return result

        # Run rules (on augmented_source so annotations are visible)
        for rule_id, rule_func in ALL_RULES.items():
            if not self._enabled.get(rule_id, True):
                continue
            try:
                diags = rule_func(tree, augmented_source)
                configured_sev = self._severities.get(rule_id)
                if configured_sev is not None:
                    diags = tuple(d.with_severity(configured_sev) for d in diags)
                # Offset diagnostics to account for preamble lines
                if not self._config.is_empty():
                    preamble_lines = preamble.count('\n')
                    diags = tuple(
                        _offset_diagnostic(d, -preamble_lines) if preamble_lines > 0 else d
                        for d in diags
                    )
                result = result.extend(diags)
            except Exception as e:
                result = result.add(Diagnostic(
                    message=f"Rule '{rule_id}' failed: {e}",
                    severity=Severity.WARNING,
                    range=Range(1, 1, 1, 1),
                    rule_id="TWIG-INTERNAL-ERROR",
                ))

        return result

    def analyze_file(self, file_path: str) -> AnalysisResult:
        """Analyze a .twig file from disk.

        Discovers .twig-analyzer.yml config by walking up from the file's directory.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        # Auto-discover config if none was explicitly set
        if self._config.is_empty():
            from pathlib import Path
            start_dir = str(Path(file_path).parent)
            self._config = TwigAnalyzerConfig.discover(start_dir)

        return self.analyze(source, file_path)

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(ALL_RULES.keys())

    @property
    def enabled_rule_ids(self) -> tuple[str, ...]:
        return tuple(rid for rid, enabled in self._enabled.items() if enabled)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _offset_diagnostic(d: Diagnostic, line_offset: int) -> Diagnostic:
    """Shift a diagnostic's line by the given offset."""
    from dataclasses import replace
    r = d.range
    new_range = replace(
        r,
        start_line=max(1, r.start_line + line_offset),
        end_line=max(1, r.end_line + line_offset),
    )
    return d.with_range(new_range)
