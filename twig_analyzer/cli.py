"""Command-line interface for Twig Static Analyzer.

Usage:
    twig-analyze path/to/templates/
    twig-analyze path/to/file.html.twig
    twig-analyze --format json path/to/templates/
    twig-analyze --disable raw-filter,hardcoded-text .
    twig-analyze --severity missing-escape=warning .

Can be extended to serve as a VS Code Language Server via the same core.
"""

import argparse
import os
import sys
from typing import List

from .analyzer import Analyzer
from .diagnostics import AnalysisResult, Severity
from .reporter import report_console, report_json, report_junit


def find_twig_files(paths: List[str]) -> List[str]:
    """Recursively find .twig and .html.twig files."""
    extensions = {".twig", ".html.twig", ".html", ".xml", ".json.twig"}
    files: List[str] = []

    for path in paths:
        if os.path.isfile(path):
            if any(path.endswith(ext) for ext in extensions):
                files.append(path)
        elif os.path.isdir(path):
            for root, _, filenames in os.walk(path):
                for fname in filenames:
                    if any(fname.endswith(ext) for ext in extensions):
                        files.append(os.path.join(root, fname))
    return sorted(files)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="twig-analyze",
        description="Twig 3.x Static Analyzer – Lint and check Twig templates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  twig-analyze templates/
  twig-analyze --format json templates/
  twig-analyze --disable raw-filter templates/
  twig-analyze --severity variable-usage=error templates/
        """,
    )

    parser.add_argument(
        "paths", nargs="+",
        help="Files or directories to analyze",
    )
    parser.add_argument(
        "--format", "-f", choices=["console", "json", "junit"],
        default="console",
        help="Output format (default: console)",
    )
    parser.add_argument(
        "--disable", "-d",
        help="Comma-separated list of rule IDs to disable",
    )
    parser.add_argument(
        "--severity", "-s", action="append",
        help="Override rule severity: rule_id=severity (e.g. raw-filter=error)",
    )
    parser.add_argument(
        "--only-errors", action="store_true",
        help="Only show errors (no warnings, info, hints)",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress output, only return exit code",
    )

    args = parser.parse_args()

    # Configure rules
    rules_config = {}
    if args.disable:
        for rule_id in args.disable.split(","):
            rule_id = rule_id.strip()
            if rule_id:
                rules_config[rule_id] = False

    # Configure severities
    severities_config = {}
    if args.severity:
        for item in args.severity:
            if "=" in item:
                rule_id, sev = item.split("=", 1)
                severities_config[rule_id.strip()] = sev.strip()

    # Create analyzer
    analyzer = Analyzer(rules=rules_config if rules_config else None,
                        severities=severities_config if severities_config else None)

    # Find files
    files = find_twig_files(args.paths)
    if not files:
        print("No Twig template files found.", file=sys.stderr)
        sys.exit(1)

    # Analyze all files
    results: List[AnalysisResult] = []
    for file_path in files:
        result = analyzer.analyze_file(file_path)
        results.append(result)

    # Report
    if args.quiet:
        # Only exit code matters
        has_errors = any(
            d.severity == Severity.ERROR
            for r in results
            for d in r.diagnostics
        )
        sys.exit(1 if has_errors else 0)

    if args.format == "json":
        print(report_json(results))
    elif args.format == "junit":
        print(report_junit(results))
    else:
        output = report_console(
            results,
            show_errors=True,
            show_warnings=not args.only_errors,
            show_info=not args.only_errors,
            show_hints=not args.only_errors,
        )
        print(output)

    # Exit code: 1 if errors found
    has_errors = any(
        d.severity == Severity.ERROR
        for r in results
        for d in r.diagnostics
    )
    sys.exit(1 if has_errors else 0)


if __name__ == "__main__":
    main()
