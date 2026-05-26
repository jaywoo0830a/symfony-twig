# VS Code Extension

The Twig Static Analyzer VS Code extension provides rich IntelliSense for `.twig` and `.html.twig` files.

## Features

### Diagnostics (Problems Panel)

Real-time static analysis as you type. Errors, warnings, and hints appear in the Problems panel and as squiggly underlines.

- **On open**: Analyzes immediately when you open a `.twig` file
- **On save**: Re-analyzes on save (configurable)
- **Manual**: `Ctrl+Shift+P` → `Twig: Analyze Current File`

### Hover Documentation

Hover over any Twig built-in tag, filter, function, or test to see its documentation.

```
┌─────────────────────────────────────────────────────┐
│ ### `date`                                          │
│                                                     │
│ Formats a date                                      │
│                                                     │
│ > Since Twig 1.0                                    │
│ > Example: `{{ post.publishedAt|date('Y-m-d') }}`   │
│                                                     │
│ [📖 Twig Docs](https://twig.symfony.com/doc/3.x...)  │
└─────────────────────────────────────────────────────┘
```

**Supported hover targets:** 140+ built-in tags, filters, functions, tests, operators, and Symfony-specific declarations.

### Code Completion (IntelliSense)

| Trigger | Context | Suggestions |
|---|---|---|
| `{%` | Tag context | Block tags, inline tags, `end*` tags |
| `\|` | After pipe in `{{ }}` | 50+ filters (`date`, `upper`, `lower`, ...) |
| Inside `{{ }}` | Expression context | 30+ functions + filters |
| `<` | HTML context | HTML tags (`div`, `span`, `form`, ...) |
| Space in HTML tag | Attribute context | HTML attributes (`class`, `id`, `src`, ...) |

### Go-to-Definition (F12 / Ctrl+Click)

Navigate to referenced templates from:

| Syntax | Example |
|---|---|
| `{% extends '...' %}` | `{% extends 'base.html.twig' %}` |
| `{% include '...' %}` | `{% include 'sidebar.html.twig' %}` |
| `{% embed '...' %}` | `{% embed 'card.html.twig' %}` |
| `{% import '...' %}` | `{% import 'macros.twig' as macros %}` |
| `{{ include('...') }}` | `{{ include('partial.twig') }}` |
| `{{ source('...') }}` | `{{ source('template.twig') }}` |
| `{{ path('...') }}` | `{{ path('blog_index') }}` |
| `{{ url('...') }}` | `{{ url('blog_index') }}` |
| `{{ asset('...') }}` | `{{ asset('images/logo.png') }}` |
| `@Bundle/...` notation | `@FrameworkBundle/Resources/views/...` |

### Document Outline (Breadcrumbs)

Shows `{% block %}` and `{% macro %}` definitions in the Outline panel and breadcrumb navigation.

### Folding

Code folding for block-level tags:

```
▶ {% block content %}...{% endblock %}
▶ {% for item in items %}...{% endfor %}
▶ {% if condition %}...{% endif %}
▶ {% macro input(...) %}...{% endmacro %}
▶ {% apply upper %}...{% endapply %}
```

### Signature Help

Shows parameter information when typing function calls:

```
{{ path(|) }}
       ↑ cursor at (
┌─────────────────────────────────────────┐
│ path(route, params?)                     │
│       ↑ bold = current parameter        │
│ route: Route name                        │
│ params: Parameters                       │
└─────────────────────────────────────────┘
```

### Formatting (Shift+Alt+F)

Formats Twig templates with proper indentation for block tags, HTML structure, and nested expressions.

### Code Actions (Quick Fix)

| Diagnostic | Quick Fix |
|---|---|
| Missing escape (`TWIG-MISSING-ESCAPE`) | Add `\|e` escape filter |
| Raw filter (`TWIG-RAW-FILTER`) | Add `\|e` escape filter |

### Document Highlight

Click on `{% if %}` / `{% endif %}`, `{% for %}` / `{% endfor %}`, etc. to highlight matching pairs.

### Rename (F2)

Rename `{% block %}` and `{% macro %}` names across the template.

### Color Preview

CSS hex colors (`#ff0000`) and `rgb()` functions are previewed inline.

### Auto-close HTML Tags

Typing `>` after an HTML tag name automatically inserts the closing tag (except void elements like `<br>`, `<img>`).

### Emmet Support

Emmet abbreviations work in `.twig` files (e.g., `div.container>ul>li*5` expands to HTML).

---

## Status Bar

The status bar shows analysis results:

```
$(check) Twig: template.html.twig – 0 errors, 2 warnings
```

Click to re-analyze the current file.

---

## Keybindings

| Action | Default Shortcut |
|---|---|
| Analyze current file | `Ctrl+Shift+P` → `Twig: Analyze Current File` |
| Format document | `Shift+Alt+F` |
| Go to definition | `F12` |
| Rename symbol | `F2` |
| Show hover | `Ctrl+K Ctrl+I` |
| Trigger completion | `Ctrl+Space` |
| Trigger signature help | `Ctrl+Shift+Space` |
