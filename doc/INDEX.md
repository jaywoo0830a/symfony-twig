# Twig Static Analyzer — How-To Guides

**Runs entirely in Docker.** No local Python, no virtualenv, no pip.

---

## Pick Your Path

| I want to… | Command | Needs |
|---|---|---|
| **Use in VS Code** | `cd vscode-extension && bash install.sh` | Docker + Node.js |
| **Run LSP server** | `./run/up.sh` | Docker |
| **Run LSP in dev mode** | `./run/up.sh --dev` | Docker |
| **Run tests** | `./run/test.sh` | Docker |
| **Run CLI** | `./run/up.sh --cli "analyze templates/"` | Docker |

> Each path builds the Docker image automatically on first run.

---

## Install VS Code Extension

```bash
cd vscode-extension && bash install.sh
# → Ctrl+Shift+P → Developer: Reload Window
# → Open .twig file → diagnostics appear
```

The installer:
1. Checks Docker is running
2. Builds `twig-analyzer-lsp` Docker image (one-time)
3. Compiles TypeScript (or uses pre-built)
4. Copies extension to VS Code

---

## Configure

### How to silence "Variable may not be defined"

Create `.twig-analyzer.yml` in project root:

```yaml
globals: [app, form, user, articles, categories]
```

### How to register custom filters / functions

```yaml
filters:  [custom_filter, markdown_to_html]
functions:[vich_uploader_asset, my_helper]
tests:    [is_valid]
tags:     [form_theme]
```

### How to declare per template

```twig
{# @var user App\Entity\User #}
{# @filter custom_filter #}
{# @function my_helper #}
```

### How to disable a rule

In VS Code settings: `"twigAnalyzer.disabledRules": ["raw-filter"]`

---

## How to use the CLI

```bash
# Analyze templates
./run/up.sh --cli "analyze templates/"

# JSON output
./run/up.sh --cli "analyze --format json templates/"

# JUnit output (CI/CD)
./run/up.sh --cli "analyze --format junit templates/"

# Format templates
./run/up.sh --cli "format templates/"

# Format check only
./run/up.sh --cli "format --check templates/"
```

---

## How to run tests

```bash
./run/test.sh                          # all tests
./run/test.sh -k "filter"              # filter by name
./run/test.sh tests/test_tags.py       # single file
```

---

## How to start the LSP server

```bash
./run/up.sh              # production (port 2087)
./run/up.sh --dev        # development (hot-reload, port 2088)
./run/down.sh            # stop
./run/down.sh --clean    # stop + remove images
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Docker not found" | Install Docker Desktop |
| "Cannot connect to Docker" | Start Docker Desktop |
| "Variable may not be defined" | Add to `.twig-analyzer.yml` `globals:` |
| "Unknown filter" | Add `{# @filter name #}` or YAML `filters:` |
| No diagnostics in VS Code | Is Docker running? `docker ps` |
| Extension not loading | `Ctrl+Shift+P` → Reload Window |

---

**[Rules Reference →](rules.md)**
