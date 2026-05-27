"""Twig Static Analyzer — pure, functional analysis pipeline.

source → parse → run rules → collect diagnostics → AnalysisResult

Design: immutable data flow, reduce/filter/map over imperative loops,
        match/case for control flow (Python 3.10+).
"""

from __future__ import annotations
from functools import reduce
from pathlib import Path
from typing import Dict, FrozenSet, Optional, Sequence, Tuple

from .parser import parse, ParseError
from .diagnostics import Diagnostic, Severity, Range, AnalysisResult
from .rules import ALL_RULES, DEFAULT_SEVERITIES
from .config import TwigAnalyzerConfig

# ═══════════════════════════════════════════════════════════════════════
# Pure helpers
# ═══════════════════════════════════════════════════════════════════════

def _offset_diagnostic(d: Diagnostic, line_offset: int) -> Diagnostic:
    """Shift a diagnostic's line numbers by offset."""
    r = d.range
    new_range = Range(
        start_line=max(1, r.start_line + line_offset),
        start_column=r.start_column,
        end_line=max(1, r.end_line + line_offset),
        end_column=r.end_column,
    )
    return d.with_range(new_range)


def _apply_severity(diags: Tuple[Diagnostic, ...], sev: Optional[Severity]) -> Tuple[Diagnostic, ...]:
    """Apply a configured severity override to diagnostics."""
    if sev is None:
        return diags
    return tuple(d.with_severity(sev) for d in diags)


def _apply_line_offset(diags: Tuple[Diagnostic, ...], offset: int) -> Tuple[Diagnostic, ...]:
    """Shift all diagnostic lines by offset."""
    if offset == 0:
        return diags
    return tuple(_offset_diagnostic(d, offset) for d in diags)


# ═══════════════════════════════════════════════════════════════════════
# Analyzer — pure pipeline
# ═══════════════════════════════════════════════════════════════════════

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
        # Enabled rules: dict comprehension (pure map over ALL_RULES)
        self._enabled: FrozenSet[str] = frozenset(
            rid for rid in ALL_RULES
            if (rules or {}).get(rid, True)
        )
        # Severity overrides
        self._severities: Dict[str, Severity] = dict(DEFAULT_SEVERITIES)
        if severities:
            self._severities.update({
                rid: Severity[sev_str.upper()]
                for rid, sev_str in severities.items()
                if sev_str.upper() in Severity.__members__
            })
        self._config = config or TwigAnalyzerConfig.empty()

    def analyze(self, source: str, file_path: str = "") -> AnalysisResult:
        """Analyze a Twig template source string. Pure: source → result.

        Config-based declarations are prepended as synthetic annotations.
        """
        result = AnalysisResult(file_path=file_path, source=source)

        # ── Build augmented source with config annotations ──
        preamble = ""
        if not self._config.is_empty():
            preamble = self._config.to_annotations() + "\n"
        augmented_source = preamble + source

        # ── Parse ──
        try:
            tree = parse(augmented_source)
        except ParseError as e:
            return result.add(Diagnostic(
                message=f"Parse error: {e}",
                severity=Severity.ERROR,
                range=Range(e.line, e.column, e.line, e.column + 1),
                rule_id="TWIG-PARSE-ERROR",
            ))

        # ── Run rules — functional reduce over enabled rules ──
        preamble_lines = preamble.count("\n")

        def run_rule(acc: AnalysisResult, rule_id: str) -> AnalysisResult:
            rule_func = ALL_RULES[rule_id]
            try:
                diags = rule_func(tree, augmented_source)
                # Apply severity override → apply line offset → extend result
                diags = _apply_severity(diags, self._severities.get(rule_id))
                diags = _apply_line_offset(diags, -preamble_lines)
                return acc.extend(diags)
            except Exception as e:
                return acc.add(Diagnostic(
                    message=f"Rule '{rule_id}' failed: {e}",
                    severity=Severity.WARNING,
                    range=Range(1, 1, 1, 1),
                    rule_id="TWIG-INTERNAL-ERROR",
                ))

        # Reduce: fold over enabled rules, threading the AnalysisResult
        result = reduce(run_rule, self._enabled, result)
        return result

    def analyze_file(self, file_path: str) -> AnalysisResult:
        """Analyze a .twig file from disk.

        Discovers .twig-analyzer.yml config by walking up from the file's directory.
        """
        source = Path(file_path).read_text(encoding="utf-8")

        # Auto-discover config if none was explicitly set
        if self._config.is_empty():
            start_dir = str(Path(file_path).parent)
            self._config = TwigAnalyzerConfig.discover(start_dir)

        return self.analyze(source, file_path)

    @property
    def rule_ids(self) -> Tuple[str, ...]:
        return tuple(ALL_RULES.keys())

    @property
    def enabled_rule_ids(self) -> Tuple[str, ...]:
        return tuple(self._enabled)
