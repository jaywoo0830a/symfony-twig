# Installation

## Python Package

Requires Python 3.9+ and Twig 3.x templates.

```bash
cd symfony-twig
pip install -e .
```

Verify:

```bash
twig-analyze --help
```

## VS Code Extension

The extension is in `vscode-extension/`. Install with:

```bash
cd vscode-extension
bash install.sh
```

Then run `Developer: Reload Window` from the VS Code command palette.

### Prerequisites

- **Python 3.9+** with the `twig_analyzer` package installed (the installer handles this)
- **Node.js** for compiling the TypeScript extension (the installer handles this)
- **VS Code 1.80+**

### Manual Build

```bash
cd vscode-extension
npm install
npm run compile
bash install.sh
```

### Uninstall

```bash
bash vscode-extension/uninstall.sh
```

## Dependencies

| Package | Purpose |
|---|---|
| `pyyaml` | `.twig-analyzer.yml` config file parsing |
| `pytest` | Running the test suite (dev only) |

Install all at once:

```bash
pip install -e ".[dev]"
```
