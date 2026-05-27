# Twig Static Analyzer

Static analysis & VS Code IntelliSense for Twig 3.x templates.

**Runs entirely in Docker.** No Python, Node.js, or virtualenv required on your machine.

---

## Quick Start

```bash
git clone <repo> && cd symfony-twig

# 1. Start the LSP server
./run/up.sh

# 2. Install the VS Code extension
bash vscode-extension/install.sh

# 3. Reload VS Code
#    Ctrl+Shift+P → Developer: Reload Window
#    Open any .twig file → done.
```

> **Prerequisite:** [Docker Desktop](https://docker.com) only.

## Stop / Uninstall

```bash
bash vscode-extension/uninstall.sh   # remove extension
./run/down.sh                        # stop server
```

## Run Tests

```bash
./run/test.sh                        # all 137 tests
./run/test.sh -k "filter"            # filter by name
./run/test.sh tests/test_tags.py     # single file
```
## Editor Features

| Action | How |
|---|---|
| **See warnings** | Open `.twig` → Problems panel (`Ctrl+Shift+M`) |
| **Hover docs** | Hover over `date`, `if`, `path()`, HTML tags |
| **Auto-complete** | Type `{%`, `\|`, `{{`, `<` → Ctrl+Space |
| **Format** | `Shift+Alt+F` |
| **Go to definition** | `F12` or Ctrl+Click on template paths |

## Quick Config: `.twig-analyzer.yml`

```yaml
globals: [app, form, user, articles]
filters:  [custom_filter, markdown_to_html]
functions:[vich_uploader_asset]
```

---

**[📖 Full How-To Guides →](doc/INDEX.md)**
