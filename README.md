# Twig Static Analyzer

Twig 3.x template static analyzer - detects syntax errors, undefined variables/filters/functions, deprecated features, and security issues.

Designed to be extensible as a VS Code extension (LSP-compatible).

## Install

```bash
cd symfony-twig
pip install -e .
```

## Usage

```bash
twig-analyze examples/
twig-analyze --format json examples/
twig-analyze --disable raw-filter examples/
twig-analyze --severity raw-filter=error examples/
twig-analyze --format junit examples/
```

## Rules

| Rule ID | Description | Default Severity |
|---------|-------------|-----------------|
| extends-first | extends must be first tag | ERROR |
| undefined-filters | Unknown filter usage | WARNING |
| undefined-functions | Unknown function usage | WARNING |
| undefined-tests | Unknown test usage | WARNING |
| deprecated-features | Deprecated tag/filter usage | WARNING |
| raw-filter | raw filter XSS risk | WARNING |
| missing-escape | Possible missing escape | HINT |
| hardcoded-text | Text needing i18n | HINT |
| variable-usage | Potentially undefined variable | WARNING |
| tag-balancing | Block tag balance check | ERROR |

## VS Code Extension Integration

```python
from twig_analyzer import Analyzer
analyzer = Analyzer()
result = analyzer.analyze(source_code, file_path="template.twig")
lsp_diagnostics = [d.to_dict() for d in result.diagnostics]
```

## Run Tests

```bash
pip install pytest
pytest tests/ -v
```

## References

- [Twig 3.x Docs](https://twig.symfony.com/doc/3.x/)
- [TwigStan](https://github.com/twigstan/twigstan)
- [Twig Language Server](https://github.com/kaermorchen/twig-language-server)
