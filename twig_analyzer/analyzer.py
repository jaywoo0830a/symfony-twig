"""Twig Static Analyzer — pure analysis pipeline.

source → parse → run rules → collect diagnostics → AnalysisResult
"""

from __future__ import annotations
from typing import Dict, Optional, Sequence

from .parser import parse, ParseError
from .diagnostics import Diagnostic, Severity, Range, AnalysisResult
from .rules import ALL_RULES, DEFAULT_SEVERITIES


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

    def analyze(self, source: str, file_path: str = "") -> AnalysisResult:
        """Analyze a Twig template source string. Pure: source → result."""
        result = AnalysisResult(file_path=file_path, source=source)

        # Parse
        try:
            tree = parse(source)
        except ParseError as e:
            result = result.add(Diagnostic(
                message=f"Parse error: {e}",
                severity=Severity.ERROR,
                range=Range(e.line, e.column, e.line, e.column + 1),
                rule_id="TWIG-PARSE-ERROR",
            ))
            return result

        # Run rules
        for rule_id, rule_func in ALL_RULES.items():
            if not self._enabled.get(rule_id, True):
                continue
            try:
                diags = rule_func(tree, source)
                configured_sev = self._severities.get(rule_id)
                if configured_sev is not None:
                    diags = tuple(d.with_severity(configured_sev) for d in diags)
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
        """Analyze a .twig file from disk."""
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        return self.analyze(source, file_path)

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(ALL_RULES.keys())

    @property
    def enabled_rule_ids(self) -> tuple[str, ...]:
        return tuple(rid for rid, enabled in self._enabled.items() if enabled)
