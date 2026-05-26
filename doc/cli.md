# CLI Reference

## Synopsis

```bash
twig-analyze analyze [options] <paths...>
twig-analyze format [options] <paths...>
```

## `analyze` — Static Analysis

### Basic Usage

```bash
# Analyze a single file
twig-analyze analyze templates/home.html.twig

# Analyze a directory (recursive)
twig-analyze analyze templates/

# Analyze multiple paths
twig-analyze analyze templates/ src/AnotherBundle/templates/
```

### Options

| Option | Short | Description |
|---|---|---|
| `--format <fmt>` | `-f` | Output format: `console`, `json`, `junit` (default: `console`) |
| `--disable <ids>` | `-d` | Comma-separated rule IDs to disable |
| `--severity <rule=sev>` | `-s` | Override rule severity (repeatable) |
| `--config <path>` | `-c` | Path to `.twig-analyzer.yml` (auto-discovered if omitted) |
| `--only-errors` | | Show only ERROR-level diagnostics |
| `--quiet` | `-q` | No output; exit code indicates errors |

### Output Formats

#### Console (default)

```
=== examples/bad_template.html.twig ===
  line 3: [ERROR] extends must be first tag (TWIG-EXTENDS-FIRST)
  line 5: [WARNING] Content outside blocks is ignored (TWIG-EXTENDS-CONTENT-OUTSIDE-BLOCK)
  line 8: [WARNING] Unknown filter 'unknowFilter' (TWIG-UNKNOWN-FILTER)
  ...

=== Summary ===
4 file(s) analyzed
1 error(s), 3 warning(s)
```

#### JSON

```bash
twig-analyze analyze --format json templates/
```

```json
{
  "files": {
    "templates/home.html.twig": [
      {
        "message": "Variable 'user' may not be defined.",
        "severity": 4,
        "range": {
          "start": {"line": 4, "character": 14},
          "end": {"line": 4, "character": 18}
        },
        "code": "TWIG-UNDEFINED-VAR",
        "source": "twig-analyzer"
      }
    ]
  },
  "diagnostics": [...],
  "summary": {
    "total": 1,
    "errors": 0,
    "warnings": 0,
    "info": 0,
    "hints": 1
  }
}
```

#### JUnit (for CI)

```bash
twig-analyze analyze --format junit templates/
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="twig-analyzer" tests="4" errors="1" failures="0">
    <testcase name="templates/home.html.twig">
      <error message="Variable 'user' may not be defined.">...</error>
    </testcase>
  </testsuite>
</testsuites>
```

### CI/CD Integration

#### GitHub Actions

```yaml
- name: Twig Static Analysis
  run: |
    pip install -e .
    twig-analyze analyze --format junit templates/ > twig-report.xml

- name: Publish JUnit
  uses: actions/upload-artifact@v4
  with:
    name: twig-analysis
    path: twig-report.xml
```

#### GitLab CI

```yaml
twig-lint:
  script:
    - pip install -e .
    - twig-analyze analyze --quiet templates/
```

#### Exit Codes

| Code | Meaning |
|---|---|
| 0 | No errors found |
| 1 | One or more ERROR-level diagnostics found |
| 1 | No Twig files found (with message on stderr) |

### Disabling Rules per Analysis

```bash
# Disable specific rules
twig-analyze analyze --disable raw-filter,hardcoded-text templates/

# Override severity
twig-analyze analyze --severity raw-filter=error templates/
twig-analyze analyze -s raw-filter=error -s variable-usage=warning templates/
```

---

## `format` — Template Formatting

### Basic Usage

```bash
# Format files in-place
twig-analyze format templates/

# Check only (exit code indicates if formatting is needed)
twig-analyze format --check templates/

# Show diff instead of modifying
twig-analyze format --diff templates/
```

### Options

| Option | Short | Description |
|---|---|---|
| `--indent <n>` | `-i` | Indent size in spaces (default: 4) |
| `--check` | `-c` | Check only, don't modify files |
| `--diff` | | Show unified diff of changes |

### Formatting Rules

- Block tags (`{% if %}`, `{% for %}`, `{% block %}`) increase indentation
- `{% else %}`, `{% elseif %}` align with their parent
- Closing tags (`{% endif %}`, `{% endfor %}`, `{% endblock %}`) decrease indentation
- HTML tags are indented based on nesting
- `{{ }}` inline expressions don't affect indentation

---

## Exit Codes Summary

| Command | Exit 0 | Exit 1 |
|---|---|---|
| `analyze` | No errors | Errors found OR no files found |
| `analyze --quiet` | No errors | Errors found |
| `format` | All formatted | Formatting errors |
| `format --check` | All clean | Some files need formatting |
| `format --diff` | All clean | Some files differ |

---

## Environment Variables

| Variable | Description |
|---|---|
| `PYTHONPATH` | Additional paths for Python module discovery |
| `HOME` | Home directory (used for venv detection in VS Code extension) |
