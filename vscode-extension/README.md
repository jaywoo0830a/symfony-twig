# Twig Static Analyzer - VS Code Extension

Twig 3.x template static analysis inside VS Code.

## Requirements

- **Python 3.9+** with `twig-analyzer` installed:
  ```bash
  pip install twig-analyzer
  ```
  Or install from source:
  ```bash
  cd symfony-twig && pip install -e .
  ```

## Features

- 🔍 Real-time analysis on open/save
- 🚨 Detects: syntax errors, undefined variables, unknown filters/functions
- ⚠️ Security warnings: `|raw` filter usage
- 📦 Deprecated feature detection
- 🌐 Hardcoded text hints for i18n

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `twigAnalyzer.enabled` | `true` | Enable/disable |
| `twigAnalyzer.runOnSave` | `true` | Analyze on save |
| `twigAnalyzer.runOnOpen` | `true` | Analyze on open |
| `twigAnalyzer.disabledRules` | `[]` | Rule IDs to disable |
| `twigAnalyzer.severityOverrides` | `{}` | Override severity |
| `twigAnalyzer.fileExtensions` | `[".twig", ".html.twig"]` | File extensions |

## Commands

- `Twig: Analyze Current File` — Manually trigger analysis

## Building

```bash
cd vscode-extension
npm install
npm run compile
```

Then press F5 to launch Extension Development Host.
