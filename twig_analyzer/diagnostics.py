"""Diagnostic model – LSP-compatible diagnostic data types.

Designed so that a VS Code Language Server can directly consume these objects.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Severity(int, Enum):
    """LSP DiagnosticSeverity values."""
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4

    def __str__(self) -> str:
        return self.name.lower()


@dataclass
class Range:
    """LSP-compatible range in a file."""
    start_line: int       # 1-indexed
    start_column: int     # 1-indexed
    end_line: int         # 1-indexed
    end_column: int       # 1-indexed

    def __repr__(self) -> str:
        return f"{self.start_line}:{self.start_column}-{self.end_line}:{self.end_column}"


@dataclass
class Diagnostic:
    """Represents a single analysis finding. Compatible with LSP Diagnostic."""
    message: str
    severity: Severity
    range: Range
    rule_id: str = ""
    source: str = "twig-analyzer"
    file_path: str = ""

    def to_dict(self) -> dict:
        """Convert to LSP Diagnostic JSON format."""
        return {
            "message": self.message,
            "severity": self.severity.value,
            "range": {
                "start": {"line": self.range.start_line - 1, "character": self.range.start_column - 1},
                "end": {"line": self.range.end_line - 1, "character": self.range.end_column - 1},
            },
            "code": self.rule_id,
            "source": self.source,
        }

    def __repr__(self) -> str:
        loc = f"{self.file_path}:" if self.file_path else ""
        return f"{loc}{self.range}: [{self.severity.name}] {self.message} ({self.rule_id})"


@dataclass
class AnalysisResult:
    """Overall analysis result for a single file."""
    file_path: str
    diagnostics: list[Diagnostic] = field(default_factory=list)
    source: str = ""

    def add(self, diagnostic: Diagnostic) -> None:
        diagnostic.file_path = self.file_path
        self.diagnostics.append(diagnostic)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == Severity.WARNING]

    @property
    def info(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == Severity.INFORMATION]

    @property
    def hints(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == Severity.HINT]
