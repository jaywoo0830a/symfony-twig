# Twig Static Analyzer — Documentation

A comprehensive static analysis tool for Twig 3.x templates with VS Code IntelliSense integration. Detects syntax errors, undefined variables/filters/functions/tests/tags, deprecated features, missing escaping, and more.

## Table of Contents

| Document | Description |
|---|---|
| [Installation](installation.md) | Python package, VS Code extension setup |
| [Configuration](configuration.md) | `.twig-analyzer.yml`, annotation syntax, per-file overrides |
| [Rules](rules.md) | All 11 analysis rules with examples |
| [VS Code Extension](vscode-extension.md) | IntelliSense, hover, completion, go-to-definition, formatting |
| [CLI Reference](cli.md) | Command-line usage, JSON/JUnit output, CI integration |

## Quick Start

```bash
pip install -e .
twig-analyze templates/
```

```yaml
# .twig-analyzer.yml (place in project root)
globals:
  - app
  - user
  - articles

filters:
  - custom_filter
```

```twig
{# templates/base.html.twig #}
{# @var user App\Entity\User #}
<h1>{{ user.name|e }}</h1>
```

## Project Structure

```
symfony-twig/
├── twig_analyzer/         # Python analyzer package
│   ├── analyzer.py        # Core analysis pipeline
│   ├── ast.py             # Immutable AST nodes (frozen dataclasses)
│   ├── builtins.py        # Twig 3.x + Symfony built-in declarations
│   ├── cli.py             # CLI entry point
│   ├── config.py          # .twig-analyzer.yml discovery & loading
│   ├── diagnostics.py     # LSP-compatible diagnostic types
│   ├── formatter.py       # Template formatter
│   ├── lexer.py           # Pure tokenizer
│   ├── parser.py          # Recursive-descent parser
│   ├── reporter.py        # Console/JSON/JUnit reporters
│   └── rules.py           # 11 analysis rules (pure functions)
├── vscode-extension/      # VS Code extension (TypeScript)
│   ├── src/extension.ts   # Extension lifecycle, analysis pipeline
│   └── src/providers.ts   # 18 IntelliSense providers
├── tests/                 # 137 pytest unit tests
├── examples/              # Sample templates
├── doc/                   # Documentation (this directory)
└── .twig-analyzer.yml     # Sample project config
```
