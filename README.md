# Twig Static Analyzer

A comprehensive static analysis tool for Twig 3.x templates with VS Code IntelliSense integration.

Detects syntax errors, undefined variables/filters/functions/tests/tags, deprecated features, missing escaping, hardcoded strings, and more.

## Documentation

**[📖 Full Documentation →](doc/INDEX.md)**

| Section | Description |
|---|---|
| [Installation](doc/installation.md) | Python package & VS Code extension setup |
| [Configuration](doc/configuration.md) | `.twig-analyzer.yml`, annotations, settings |
| [Rules](doc/rules.md) | All 11 analysis rules with examples |
| [VS Code Extension](doc/vscode-extension.md) | IntelliSense, hover, completion, go-to-definition |
| [CLI Reference](doc/cli.md) | Command-line usage, JSON/JUnit, CI integration |

## Quick Start

```bash
pip install -e .
twig-analyze templates/
```

## Features

- **11 analysis rules** — extends placement, undefined names, deprecations, security, i18n
- **Project config** — `.twig-analyzer.yml` with auto-discovery (ESLint-style)
- **Per-file annotations** — `{# @var user Type #}`, `{# @filter name #}`, etc.
- **VS Code IntelliSense** — diagnostics, hover, completion, go-to-definition, formatting, folding, signature help, rename, color preview
- **JSON/JUnit output** — CI/CD integration ready
- **Pure functional design** — frozen dataclasses, immutable AST, pure rule functions
- **137 unit tests** — based on official Twig 3.x documentation

## Run Tests

```bash
pip install pytest
pytest tests/ -v
```

## License

MIT
