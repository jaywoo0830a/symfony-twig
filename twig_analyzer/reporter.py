"""Twig Analyzer Reporter – formats analysis results for output.

Supports multiple output formats:
- console: Human-readable colored terminal output
- json: Machine-readable LSP-compatible JSON
- junit: JUnit XML format (for CI/CD integration)
"""

import json
import sys
from typing import List

from .diagnostics import Diagnostic, Severity, AnalysisResult

# Optional color support
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    _HAS_COLOR = True
except ImportError:
    _HAS_COLOR = False
    # Dummy Fore/Style for no-color mode
    class _Dummy:
        def __getattr__(self, name):
            return ""
    Fore = _Dummy()
    Style = _Dummy()


def report_console(results: List[AnalysisResult], show_errors: bool = True,
                   show_warnings: bool = True, show_info: bool = True,
                   show_hints: bool = True) -> str:
    """Generate a human-readable console report.

    Args:
        results: List of analysis results (one per file).
        show_errors/show_warnings/show_info/show_hints: Filter by severity.

    Returns:
        Formatted string for terminal output.
    """
    lines: List[str] = []
    total_errors = 0
    total_warnings = 0
    total_info = 0
    total_hints = 0

    for result in results:
        if not result.diagnostics:
            continue

        # Filter by severity settings
        diags = [d for d in result.diagnostics
                 if (show_errors and d.severity == Severity.ERROR)
                 or (show_warnings and d.severity == Severity.WARNING)
                 or (show_info and d.severity == Severity.INFORMATION)
                 or (show_hints and d.severity == Severity.HINT)]

        if not diags:
            continue

        lines.append(f"\n{Fore.CYAN}{Style.BRIGHT}📄 {result.file_path}{Style.RESET_ALL}")

        for diag in diags:
            color = _severity_color(diag.severity)
            icon = _severity_icon(diag.severity)
            lines.append(
                f"  {icon} {color}{diag.range.start_line}:{diag.range.start_column}"
                f"{Style.RESET_ALL}  {diag.message}"
                f"  {Fore.BLACK}{Style.DIM}({diag.rule_id}){Style.RESET_ALL}"
            )

            if diag.severity == Severity.ERROR:
                total_errors += 1
            elif diag.severity == Severity.WARNING:
                total_warnings += 1
            elif diag.severity == Severity.INFORMATION:
                total_info += 1
            elif diag.severity == Severity.HINT:
                total_hints += 1

    # Summary
    lines.append("")
    lines.append(f"{Fore.CYAN}{'─' * 50}{Style.RESET_ALL}")
    summary_parts = []
    if total_errors > 0:
        summary_parts.append(f"{Fore.RED}{total_errors} error(s){Style.RESET_ALL}")
    if total_warnings > 0:
        summary_parts.append(f"{Fore.YELLOW}{total_warnings} warning(s){Style.RESET_ALL}")
    if total_info > 0:
        summary_parts.append(f"{Fore.BLUE}{total_info} info{Style.RESET_ALL}")
    if total_hints > 0:
        summary_parts.append(f"{Fore.BLACK}{total_hints} hint(s){Style.RESET_ALL}")

    if summary_parts:
        lines.append(f"Found: {', '.join(summary_parts)}")
    else:
        lines.append(f"{Fore.GREEN}✓ No issues found.{Style.RESET_ALL}")

    lines.append(f"{Fore.CYAN}{'─' * 50}{Style.RESET_ALL}")
    lines.append("")

    return "\n".join(lines)


def report_json(results: List[AnalysisResult]) -> str:
    """Generate LSP-compatible JSON output.

    Returns a JSON string with per-file diagnostics in LSP format,
    suitable for consumption by VS Code or other tools.
    """
    output: dict = {"files": {}}

    for result in results:
        output["files"][result.file_path] = [d.to_dict() for d in result.diagnostics]

    # Also provide a flat list for LSP
    all_diags = []
    for result in results:
        all_diags.extend([d.to_dict() for d in result.diagnostics])
    output["diagnostics"] = all_diags
    output["summary"] = {
        "total": len(all_diags),
        "errors": sum(1 for d in all_diags if d["severity"] == Severity.ERROR.value),
        "warnings": sum(1 for d in all_diags if d["severity"] == Severity.WARNING.value),
        "info": sum(1 for d in all_diags if d["severity"] == Severity.INFORMATION.value),
        "hints": sum(1 for d in all_diags if d["severity"] == Severity.HINT.value),
    }

    return json.dumps(output, indent=2, ensure_ascii=False)


def report_junit(results: List[AnalysisResult]) -> str:
    """Generate JUnit XML report format for CI/CD integration."""
    import xml.etree.ElementTree as ET
    from xml.dom import minidom

    testsuite = ET.Element("testsuite", {
        "name": "twig-analyzer",
        "tests": str(sum(len(r.diagnostics) for r in results)),
    })

    for result in results:
        for diag in result.diagnostics:
            testcase = ET.SubElement(testsuite, "testcase", {
                "classname": result.file_path,
                "name": f"{diag.rule_id}: {diag.message[:80]}",
                "line": str(diag.range.start_line),
            })
            if diag.severity == Severity.ERROR:
                ET.SubElement(testcase, "failure", {
                    "message": diag.message,
                    "type": diag.rule_id,
                })
            elif diag.severity == Severity.WARNING:
                ET.SubElement(testcase, "skipped", {
                    "message": diag.message,
                })

    xml_str = ET.tostring(testsuite, encoding="unicode")
    return minidom.parseString(xml_str).toprettyxml(indent="  ")


def _severity_color(sev: Severity) -> str:
    if not _HAS_COLOR:
        return ""
    return {
        Severity.ERROR: Fore.RED + Style.BRIGHT,
        Severity.WARNING: Fore.YELLOW + Style.BRIGHT,
        Severity.INFORMATION: Fore.BLUE,
        Severity.HINT: Fore.BLACK + Style.DIM,
    }.get(sev, "")


def _severity_icon(sev: Severity) -> str:
    return {
        Severity.ERROR: "❌",
        Severity.WARNING: "⚠️",
        Severity.INFORMATION: "ℹ️",
        Severity.HINT: "💡",
    }.get(sev, "•")
