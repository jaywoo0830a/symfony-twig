# Analysis Rules

All 11 rules with examples, severity levels, and suppression methods.

---

## TWIG-EXTENDS-FIRST

**Severity:** `ERROR`

`{% extends %}` must be the first non-comment, non-whitespace tag in the template.

```twig
{# ❌ Wrong #}
<p>Some text</p>
{% extends 'base.html.twig' %}

{# ✅ Correct #}
{% extends 'base.html.twig' %}
<p>Some text</p>
```

Comments and whitespace before `{% extends %}` are allowed.

---

## TWIG-EXTENDS-CONTENT-OUTSIDE-BLOCK

**Severity:** `WARNING`

When using `{% extends %}`, any content outside `{% block %}` tags is silently ignored by Twig.

```twig
{% extends 'base.html.twig' %}

<p>This text is ignored!</p>       {# ⚠️ WARNING #}

{% block content %}
    <p>This text renders.</p>      {# ✅ #}
{% endblock %}
```

---

## TWIG-UNKNOWN-FILTER

**Severity:** `WARNING`

A filter name not in the built-in list or declared via config/annotations.

```twig
{{ data|unknown_filter }}          {# ⚠️ Unknown filter #}
{{ data|upper }}                   {# ✅ Built-in #}
```

**Suppress:** Add to `.twig-analyzer.yml` or use `{# @filter unknown_filter #}`.

---

## TWIG-UNKNOWN-FUNCTION

**Severity:** `WARNING`

A function call not in the built-in list or declared via config/annotations.

```twig
{{ unknown_func() }}               {# ⚠️ Unknown function #}
{{ path('route_name') }}           {# ✅ Built-in Symfony function #}
```

**Suppress:** Add to `.twig-analyzer.yml` or use `{# @function unknown_func #}`.

---

## TWIG-UNKNOWN-TEST

**Severity:** `WARNING`

A test (`is` expression) not in the built-in list or declared via config/annotations.

```twig
{% if obj is unknown_test %}       {# ⚠️ Unknown test #}
{% if obj is defined %}            {# ✅ Built-in #}
```

**Suppress:** Add to `.twig-analyzer.yml` or use `{# @test unknown_test #}`.

---

## TWIG-UNKNOWN-TAG

**Severity:** `WARNING`

A tag not in the built-in list or declared via config/annotations.

```twig
{% unknown_tag %}                  {# ⚠️ Unknown tag #}
{% if condition %}                 {# ✅ Built-in #}
```

**Suppress:** Add to `.twig-analyzer.yml` or use `{# @tag unknown_tag #}`.

---

## TWIG-DEPRECATED-TAG / TWIG-DEPRECATED-FILTER

**Severity:** `WARNING`

Usage of Twig features deprecated in 3.x:

| Feature | Type | Deprecated | Replacement |
|---|---|---|---|
| `{% spaceless %}` | tag | 3.7 | `{% apply spaceless %}` |
| `\|spaceless` | filter | 3.7 | `{% apply spaceless %}` |
| `{% include %}` | tag | 3.12 | `{{ include() }}` function |

---

## TWIG-RAW-FILTER

**Severity:** `WARNING`

The `|raw` filter disables auto-escaping and can cause XSS vulnerabilities.

```twig
{{ user_input|raw }}               {# ⚠️ Security risk #}
{{ safe_html|raw }}                {# ⚠️ Verify this is intentional #}
```

---

## TWIG-MISSING-ESCAPE

**Severity:** `HINT`

Variables output without an explicit escape filter. In Twig 3.x, auto-escaping is enabled by default, so this is a HINT, not an ERROR.

```twig
{{ user.name }}                    {# ℹ️ Consider adding |e #}
{{ user.name|e }}                  {# ✅ Explicitly escaped #}
```

---

## TWIG-HARDCODED-TEXT

**Severity:** `HINT`

Hardcoded text strings that may need internationalization (i18n).

```twig
<p>Welcome to our site!</p>        {# ℹ️ Consider using {% trans %} #}
```

---

## TWIG-UNDEFINED-VAR

**Severity:** `HINT` (not WARNING — controller variables are external)

A variable that is not defined via `{% set %}`, `{% for %}`, `{% types %}`, `{# @var #}`, or `.twig-analyzer.yml` config.

```twig
{{ user.name }}                    {# ℹ️ if 'user' not declared anywhere #}
```

**Suppress:** Add to `.twig-analyzer.yml` globals, or use `{% types %}` tag, or `{# @var user Type #}` annotation.

---

## Disabling Rules

### Per-analysis (CLI)

```bash
twig-analyze --disable raw-filter,hardcoded-text templates/
```

### Per-analysis (VS Code)

```json
"twigAnalyzer.disabledRules": ["raw-filter", "hardcoded-text"]
```

### Severity Override

```bash
twig-analyze --severity raw-filter=error --severity variable-usage=warning templates/
```

```json
"twigAnalyzer.severityOverrides": {
    "raw-filter": "error",
    "variable-usage": "warning"
}
```
