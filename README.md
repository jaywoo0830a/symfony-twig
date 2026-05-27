# Twig Static Analyzer

Static analysis & VS Code IntelliSense for Twig 3.x templates.

**Runs entirely in Docker. No local Python, Node.js, or virtualenv required.**

---

## Quick Start

```bash
git clone <repo> && cd symfony-twig

# Install VS Code extension (Docker handles everything)
cd vscode-extension && bash install.sh
# → Ctrl+Shift+P → Developer: Reload Window
# → Open any .twig file — done.
```

> **Prerequisite:** [Docker Desktop](https://docker.com) only. Nothing else.

---

## How Do I…?

| I want to… | How |
|---|---|
| **Install in VS Code** | `cd vscode-extension && bash install.sh` |
| **See warnings in editor** | Open `.twig` → Problems panel (`Ctrl+Shift+M`) |
| **Get docs when hovering** | Hover over `date`, `if`, `path()`, HTML tags |
| **Auto-complete** | Type `{%` → Ctrl+Space (tags, filters, functions, HTML) |
| **Suppress "undefined variable"** | Add to `.twig-analyzer.yml` `globals:` |
| **Register custom filters** | Add `{# @filter my_filter #}` comment |
| **Format a template** | `Shift+Alt+F` |
| **Jump to included template** | `F12` or Ctrl+Click |
| **Run LSP server** | `./run/up.sh` |
| **Run LSP in dev mode** | `./run/up.sh --dev` |
| **Run tests** | `./run/test.sh` |
| **Run CLI analysis** | `./run/up.sh --cli "analyze templates/"` |

---

## Quick Config: `.twig-analyzer.yml`

```yaml
globals: [app, form, user, articles]
filters:  [custom_filter, markdown_to_html]
functions:[vich_uploader_asset]
```

---

**[📖 Full How-To Guides →](doc/INDEX.md)**
