# Configuration

Twig Analyzer uses a layered declaration system. Declarations from all sources are merged, so you can mix project-wide config with per-file annotations.

## Layered Declaration System

```
┌──────────────────────────────────────────────┐
│ 3. {# @var user #}  ←  per-file annotations │  highest priority
├──────────────────────────────────────────────┤
│ 2. child/.twig-analyzer.yml  ←  subdirectory │
├──────────────────────────────────────────────┤
│ 1. root/.twig-analyzer.yml  ←  project root  │  lowest priority
└──────────────────────────────────────────────┘
```

All layers are **merged** (union of sets). A variable declared anywhere is recognized everywhere.

---

## `.twig-analyzer.yml` — Project-Wide Config

Place this file in your project root. It is **auto-discovered** by walking up from each template file's directory.

### Schema

```yaml
# .twig-analyzer.yml

# ── Global variables (controller-passed, always available) ──
globals:
  - app
  - form
  - user
  - articles

# ── Custom Twig filters ──
filters:
  - markdown_to_html
  - custom_price_format

# ── Custom Twig functions ──
functions:
  - vich_uploader_asset
  - setting

# ── Custom Twig tests ──
tests:
  - is_valid
  - instanceof

# ── Custom Twig tags ──
tags:
  - form_theme
  - my_custom_tag
```

### Discovery

The analyzer walks up from the template file's directory, looking for:

1. `.twig-analyzer.yml`
2. `.twig-analyzer.yaml`
3. `.twiganalyzer.yml`

If multiple config files exist (e.g., one in `/project/` and one in `/project/templates/blog/`), their declarations are merged. The closest config to the template file takes precedence for any conflicts.

### CLI Override

```bash
twig-analyze --config /path/to/special-config.yml templates/
```

---

## `{# @... #}` — Per-File Annotations

Annotations are Twig comments that declare variables, filters, functions, tests, or tags for a single template file. Place them at the top of your template (before or after `{% extends %}`).

### Variable Annotations

```twig
{# @var user App\Entity\User #}
{# @var notifications array #}
{# @param items iterable #}
{% extends 'base.html.twig' %}

<h1>{{ user.name|e }}</h1>       {# ✅ recognized #}
<p>{{ unknown_var }}</p>          {# ⚠️ "may not be defined" #}
```

### Filter Annotations

```twig
{# @filter markdown_to_html #}
{# @filter custom_filter #}

{{ content|markdown_to_html }}   {# ✅ recognized #}
{{ data|custom_filter }}         {# ✅ recognized #}
```

### Function Annotations

```twig
{# @function vich_uploader_asset #}
{# @function my_helper #}

<img src="{{ vich_uploader_asset(product) }}">
```

### Test Annotations

```twig
{# @test is_valid #}
{# @test instanceof #}

{% if obj is is_valid %}...{% endif %}
```

### Tag Annotations

```twig
{# @tag my_block #}
{# @tag endmy_block #}

{% my_block %}...{% endmy_block %}
```

### Bundle Annotations

You can declare multiple items in one comment block:

```twig
{#
 # @var user App\Entity\User
 # @var articles iterable
 # @filter markdown_to_html
 # @function vich_uploader_asset
 #}
{% extends 'base.html.twig' %}
```

---

## Built-in Declarations

These are always recognized — no configuration needed:

### Symfony Globals
`app`, `form`

### Twig Built-in Globals
`_self`, `_context`, `_charset`, `loop`

### Symfony Tags (auto-recognized)
`form_theme`, `trans`, `trans_default_domain`, `stopwatch`

### Variable Definitions
`{% set name = value %}` and `{% for item in items %}` variables are automatically recognized.

---

## VS Code Settings

Available in VS Code settings (`Ctrl+,` → search `twigAnalyzer`):

| Setting | Type | Default | Description |
|---|---|---|---|
| `twigAnalyzer.enabled` | boolean | `true` | Enable/disable analysis |
| `twigAnalyzer.runOnOpen` | boolean | `true` | Analyze when opening a file |
| `twigAnalyzer.runOnSave` | boolean | `true` | Analyze on save |
| `twigAnalyzer.fileExtensions` | string[] | `[".twig", ".html.twig"]` | File extensions to analyze |
| `twigAnalyzer.pythonPath` | string | `""` | Custom Python interpreter path |
| `twigAnalyzer.disabledRules` | string[] | `[]` | Rule IDs to disable |
| `twigAnalyzer.severityOverrides` | object | `{}` | Per-rule severity overrides |
