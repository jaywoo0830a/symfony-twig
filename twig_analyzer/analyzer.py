"""Twig Static Analyzer – core analysis engine.

Takes source text, runs all rules, returns diagnostics.
Designed to be called from both CLI and VS Code extension (LSP server).
"""

from typing import Callable, Dict, List, Optional

from .parser import Parser, ParseError
from .diagnostics import Diagnostic, Severity, Range, AnalysisResult
from .rules import ALL_RULES, DEFAULT_SEVERITIES
from .ast import TemplateNode


class Analyzer:
    """Core static analyzer for Twig templates.

    Usage:
        analyzer = Analyzer()
        result = analyzer.analyze("{{ user.name }}", file_path="template.html.twig")
        for diag in result.diagnostics:
            print(diag)

    For VS Code extension integration:
        # The result.diagnostics are LSP-compatible (use diag.to_dict())
        lsp_diagnostics = [d.to_dict() for d in result.diagnostics]
    """

    def __init__(self, rules: Optional[Dict[str, bool]] = None,
                 severities: Optional[Dict[str, str]] = None):
        """Initialize the analyzer with optional rule configuration.

        Args:
            rules: Dict of rule_id -> enabled (True/False). None means all enabled.
            severities: Dict of rule_id -> severity string ('error'|'warning'|'info'|'hint').
                        None means use defaults.
        """
        self._enabled_rules: Dict[str, bool] = {}
        self._severities: Dict[str, Severity] = dict(DEFAULT_SEVERITIES)

        # Configure enabled rules
        for rule_id in ALL_RULES:
            if rules and rule_id in rules:
                self._enabled_rules[rule_id] = rules[rule_id]
            else:
                self._enabled_rules[rule_id] = True

        # Configure severities
        if severities:
            for rule_id, sev_str in severities.items():
                try:
                    self._severities[rule_id] = Severity[sev_str.upper()]
                except KeyError:
                    pass

    def analyze(self, source: str, file_path: str = "") -> AnalysisResult:
        """Analyze a Twig template source string.

        Args:
            source: The Twig template source code.
            file_path: Optional file path for error reporting.

        Returns:
            AnalysisResult containing all diagnostics.
        """
        result = AnalysisResult(file_path=file_path, source=source)

        # Parse
        try:
            tree = Parser(source).parse()
        except ParseError as e:
            result.add(Diagnostic(
                message=f"Parse error: {e}",
                severity=Severity.ERROR,
                range=Range(e.line, e.column, e.line, e.column + 1),
                rule_id="TWIG-PARSE-ERROR",
            ))
            return result

        # Run all enabled rules
        for rule_id, rule_func in ALL_RULES.items():
            if not self._enabled_rules.get(rule_id, True):
                continue

            try:
                diags = rule_func(tree, source)
                # Override severity based on configuration
                configured_sev = self._severities.get(rule_id)
                for diag in diags:
                    if configured_sev:
                        diag.severity = configured_sev
                    result.add(diag)
            except Exception as e:
                result.add(Diagnostic(
                    message=f"Rule '{rule_id}' failed: {e}",
                    severity=Severity.WARNING,
                    range=Range(1, 1, 1, 1),
                    rule_id="TWIG-INTERNAL-ERROR",
                ))

        return result

    def analyze_file(self, file_path: str) -> AnalysisResult:
        """Analyze a Twig template file.

        Args:
            file_path: Path to the .twig file.

        Returns:
            AnalysisResult containing all diagnostics.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        return self.analyze(source, file_path)

    @property
    def rule_ids(self) -> List[str]:
        """Get list of all available rule IDs."""
        return list(ALL_RULES.keys())

    @property
    def enabled_rule_ids(self) -> List[str]:
        """Get list of enabled rule IDs."""
        return [rid for rid, enabled in self._enabled_rules.items() if enabled]
