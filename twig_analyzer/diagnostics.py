"""Diagnostic model — immutable LSP-compatible types.

All types are frozen dataclasses. Conversions to LSP JSON are pure functions.
"""

from __future__ import annotations
from dataclasses import dataclass, field, replace
from enum import IntEnum
from typing import Dict, List, Sequence, Tuple


class Severity(IntEnum):
    """LSP DiagnosticSeverity — numeric for JSON serialization."""
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


@dataclass(frozen=True)
class Range:
    """LSP-compatible range (1-indexed)."""
    start_line: int
    start_column: int
    end_line: int
    end_column: int

    def __repr__(self) -> str:
        return f"{self.start_line}:{self.start_column}-{self.end_line}:{self.end_column}"

    def to_lsp(self) -> dict:
        """Convert to LSP Range (0-indexed)."""
        return {
            "start": {"line": self.start_line - 1, "character": self.start_column - 1},
            "end":   {"line": self.end_line - 1,   "character": self.end_column - 1},
        }


@dataclass(frozen=True)
class Diagnostic:
    """A single analysis finding. Immutable."""
    message: str
    severity: Severity
    range: Range
    rule_id: str = ""
    source: str = "twig-analyzer"
    file_path: str = ""

    def with_severity(self, sev: Severity) -> Diagnostic:
        return replace(self, severity=sev)

    def with_file(self, path: str) -> Diagnostic:
        return replace(self, file_path=path)

    def with_range(self, r: Range) -> Diagnostic:
        return replace(self, range=r)

    def to_lsp(self) -> dict:
        """Convert to LSP Diagnostic JSON."""
        return {
            "message": self.message,
            "severity": int(self.severity),
            "range": self.range.to_lsp(),
            "code": self.rule_id,
            "source": self.source,
        }

    def __repr__(self) -> str:
        loc = f"{self.file_path}:" if self.file_path else ""
        return f"{loc}{self.range}: [{self.severity.name}] {self.message} ({self.rule_id})"


@dataclass(frozen=True)
class AnalysisResult:
    """Analysis result for a single file. Immutable."""
    file_path: str = ""
    diagnostics: Tuple[Diagnostic, ...] = ()
    source: str = ""

    def add(self, diag: Diagnostic) -> AnalysisResult:
        """Return a new AnalysisResult with one diagnostic added."""
        return replace(
            self,
            diagnostics=self.diagnostics + (diag.with_file(self.file_path),),
        )

    def extend(self, diags: Sequence[Diagnostic]) -> AnalysisResult:
        """Return a new AnalysisResult with multiple diagnostics added."""
        new_diags = tuple(d.with_file(self.file_path) for d in diags)
        return replace(self, diagnostics=self.diagnostics + new_diags)

    @property
    def errors(self) -> Tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == Severity.ERROR)

    @property
    def warnings(self) -> Tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == Severity.WARNING)

    @property
    def infos(self) -> Tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == Severity.INFORMATION)

    @property
    def hints(self) -> Tuple[Diagnostic, ...]:
        return tuple(d for d in self.diagnostics if d.severity == Severity.HINT)

    @property
    def has_errors(self) -> bool:
        return any(d.severity == Severity.ERROR for d in self.diagnostics)
