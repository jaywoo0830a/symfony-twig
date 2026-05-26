"""CLI entry point — pure argument parsing → function dispatch."""

from __future__ import annotations
import argparse
import os
import sys
from typing import List, Sequence


def find_twig_files(paths: Sequence[str]) -> List[str]:
    """Find all Twig template files under given paths."""
    extensions = frozenset({".twig", ".html.twig", ".html", ".xml", ".json.twig"})
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


def cmd_analyze(args: argparse.Namespace) -> None:
    from .analyzer import Analyzer
    from .diagnostics import Severity
    from .reporter import report_console, report_json, report_junit
    from .config import TwigAnalyzerConfig

    rules_config: dict[str, bool] = {}
    if args.disable:
        for rid in args.disable.split(","):
            rid = rid.strip()
            if rid:
                rules_config[rid] = False

    sev_config: dict[str, str] = {}
    if args.severity:
        for item in args.severity:
            if "=" in item:
                rid, sev = item.split("=", 1)
                sev_config[rid.strip()] = sev.strip()

    # Load config: explicit --config flag or auto-discover from first file
    config = TwigAnalyzerConfig.empty()
    files = find_twig_files(args.paths)
    if not files:
        print("No Twig template files found.", file=sys.stderr)
        sys.exit(1)

    if args.config:
        config = TwigAnalyzerConfig._load_file(args.config)
    else:
        start_dir = os.path.dirname(os.path.abspath(files[0]))
        config = TwigAnalyzerConfig.discover(start_dir)

    analyzer = Analyzer(rules=rules_config or None, severities=sev_config or None, config=config)

    results = [analyzer.analyze_file(f) for f in files]

    if args.quiet:
        has_err = any(r.has_errors for r in results)
        sys.exit(1 if has_err else 0)

    if args.format == "json":
        print(report_json(results))
    elif args.format == "junit":
        print(report_junit(results))
    else:
        print(report_console(
            results,
            show_warnings=not args.only_errors,
            show_info=not args.only_errors,
            show_hints=not args.only_errors,
        ))

    has_err = any(r.has_errors for r in results)
    sys.exit(1 if has_err else 0)


def cmd_format(args: argparse.Namespace) -> None:
    from .formatter import format_twig

    files = find_twig_files(args.paths)
    if not files:
        print("No Twig template files found.", file=sys.stderr)
        sys.exit(1)

    changed = 0
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            original = f.read()
        formatted = format_twig(original, indent_size=args.indent)

        if args.check:
            if original != formatted:
                print(f"Would reformat: {fp}")
                changed += 1
        elif args.diff:
            if original != formatted:
                import difflib
                diff = difflib.unified_diff(
                    original.splitlines(True), formatted.splitlines(True),
                    fromfile=fp, tofile=fp + " (formatted)",
                )
                sys.stdout.writelines(diff)
                changed += 1
        else:
            if original != formatted:
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(formatted)
                print(f"Formatted: {fp}")
                changed += 1

    if args.check:
        sys.exit(1 if changed else 0)
    elif args.diff:
        sys.exit(1 if changed else 0)


def main() -> None:
    parser = argparse.ArgumentParser(prog="twig-analyze", description="Twig 3.x Static Analyzer & Formatter")
    sub = parser.add_subparsers(dest="command")

    ap = sub.add_parser("analyze", help="Analyze templates")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--format", "-f", choices=["console", "json", "junit"], default="console")
    ap.add_argument("--disable", "-d")
    ap.add_argument("--severity", "-s", action="append")
    ap.add_argument("--only-errors", action="store_true")
    ap.add_argument("--quiet", "-q", action="store_true")
    ap.add_argument("--config", "-c", help="Path to .twig-analyzer.yml (auto-discovered if omitted)")

    fp = sub.add_parser("format", help="Format Twig templates")
    fp.add_argument("paths", nargs="+")
    fp.add_argument("--indent", "-i", type=int, default=4)
    fp.add_argument("--check", "-c", action="store_true")
    fp.add_argument("--diff", action="store_true")

    raw_args = sys.argv[1:]
    if raw_args and raw_args[0] in ("analyze", "format"):
        args = parser.parse_args(raw_args)
    else:
        args = parser.parse_args(["analyze"] + raw_args)

    if args.command == "format":
        cmd_format(args)
    else:
        cmd_analyze(args)


if __name__ == "__main__":
    main()
