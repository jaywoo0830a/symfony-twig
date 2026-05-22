"""Reporter — pure formatters for analysis results.

Formats: console (colored), JSON (LSP), JUnit XML.
"""

from __future__ import annotations
import json
import sys
from typing import List, Sequence

from .diagnostics import Diagnostic, Severity, AnalysisResult

# Optional color
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    _HAS_COLOR = True
except ImportError:
    _HAS_COLOR = False

    class _Dummy:
        def __getattr__(self, name: str) -> str: return ""
    Fore = _Dummy()
    Style = _Dummy()


def _severity_color(sev: Severity) -> str:
    return {
        Severity.ERROR: Fore.RED,
        Severity.WARNING: Fore.YELLOW,
        Severity.INFORMATION: Fore.BLUE,
        Severity.HINT: Fore.BLACK,
    }.get(sev, "")


def _severity_icon(sev: Severity) -> str:
    return {
        Severity.ERROR: "\u274c",   # ❌
        Severity.WARNING: "\u26a0\ufe0f",  # ⚠️
        Severity.INFORMATION: "\u2139\ufe0f",  # ℹ️
        Severity.HINT: "\U0001f4a1",  # 💡
    }.get(sev, "?")


def report_console(
    results: Sequence[AnalysisResult],
    show_errors: bool = True,
    show_warnings: bool = True,
    show_info: bool = True,
    show_hints: bool = True,
) -> str:
    lines: List[str] = []
    total = {"errors": 0, "warnings": 0, "info": 0, "hints": 0}

    for result in results:
        if not result.diagnostics:
            continue

        filtered = [
            d for d in result.diagnostics
            if (show_errors and d.severity == Severity.ERROR)
            or (show_warnings and d.severity == Severity.WARNING)
            or (show_info and d.severity == Severity.INFORMATION)
            or (show_hints and d.severity == Severity.HINT)
        ]
        if not filtered:
            continue

        lines.append(f"\n{Fore.CYAN}{Style.BRIGHT}\U0001f4c4 {result.file_path}{Style.RESET_ALL}")

        for d in filtered:
            color = _severity_color(d.severity)
            icon = _severity_icon(d.severity)
            lines.append(
                f"  {icon} {color}{d.range.start_line}:{d.range.start_column}"
                f"{Style.RESET_ALL}  {d.message}"
                f"  {Fore.BLACK}{Style.DIM}({d.rule_id}){Style.RESET_ALL}"
            )
            key = {Severity.ERROR: "errors", Severity.WARNING: "warnings",
                   Severity.INFORMATION: "info", Severity.HINT: "hints"}[d.severity]
            total[key] += 1

    lines.append("")
    lines.append(f"{Fore.CYAN}{'\u2500' * 50}{Style.RESET_ALL}")
    parts = []
    if total["errors"]:
        parts.append(f"{Fore.RED}{total['errors']} error(s){Style.RESET_ALL}")
    if total["warnings"]:
        parts.append(f"{Fore.YELLOW}{total['warnings']} warning(s){Style.RESET_ALL}")
    if total["info"]:
        parts.append(f"{Fore.BLUE}{total['info']} info{Style.RESET_ALL}")
    if total["hints"]:
        parts.append(f"{Fore.BLACK}{total['hints']} hint(s){Style.RESET_ALL}")

    lines.append(f"Found: {', '.join(parts)}" if parts else f"{Fore.GREEN}\u2713 No issues found.{Style.RESET_ALL}")
    lines.append(f"{Fore.CYAN}{'\u2500' * 50}{Style.RESET_ALL}")
    lines.append("")
    return "\n".join(lines)


def report_json(results: Sequence[AnalysisResult]) -> str:
    output: dict = {"files": {}}
    for r in results:
        output["files"][r.file_path] = [d.to_lsp() for d in r.diagnostics]

    all_diags = [d.to_lsp() for r in results for d in r.diagnostics]
    output["diagnostics"] = all_diags
    output["summary"] = {
        "total": len(all_diags),
        "errors": sum(1 for d in all_diags if d["severity"] == Severity.ERROR),
        "warnings": sum(1 for d in all_diags if d["severity"] == Severity.WARNING),
        "info": sum(1 for d in all_diags if d["severity"] == Severity.INFORMATION),
        "hints": sum(1 for d in all_diags if d["severity"] == Severity.HINT),
    }
    return json.dumps(output, indent=2, ensure_ascii=False)


def report_junit(results: Sequence[AnalysisResult]) -> str:
    import xml.etree.ElementTree as ET
    all_count = sum(len(r.diagnostics) for r in results)
    suite = ET.Element("testsuite", {"name": "twig-analyzer", "tests": str(all_count)})
    for r in results:
        for d in r.diagnostics:
            tc = ET.SubElement(suite, "testcase", {
                "classname": r.file_path,
                "name": f"{d.rule_id}: {d.message[:80]}",
                "line": str(d.range.start_line),
            })
            if d.severity == Severity.ERROR:
                ET.SubElement(tc, "failure", {"message": d.message})
    from xml.dom import minidom
    return minidom.parseString(ET.tostring(suite, "unicode")).toprettyxml(indent="  ")
