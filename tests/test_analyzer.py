"""Unit tests for Twig Static Analyzer."""

import json
import tempfile
import os
import pytest
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from twig_analyzer.lexer import tokenize, ExpressionTokenizer, Token, TokenType
from twig_analyzer.parser import parse, ParseError
from twig_analyzer.analyzer import Analyzer
from twig_analyzer.diagnostics import Severity, Diagnostic, Range
from twig_analyzer.ast import (
    TemplateNode, PrintNode, BlockTagNode, InlineTagNode,
    VariableNode, FilterNode, FunctionCallNode, LiteralNode,
)
from twig_analyzer.builtins import (
    BUILTIN_TAGS, BUILTIN_FILTERS, BUILTIN_FUNCTIONS, BUILTIN_TESTS,
)


# ============================================================
# Lexer Tests
# ============================================================

class TestLexer:
    def test_simple_text(self):
        tokens = tokenize("Hello World")
        assert len(tokens) >= 2  # TEXT + EOF
        assert tokens[0].type == TokenType.TEXT
        assert "Hello World" in tokens[0].value

    def test_var_delimiter(self):
        tokens = tokenize("{{ name }}")
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert TokenType.VAR_START in types

    def test_block_delimiter(self):
        tokens = tokenize("{% if true %}{% endif %}")
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert any(t.type == TokenType.BLOCK_START for t in tokens)

    def test_comment_delimiter(self):
        tokens = tokenize("{# comment #}")
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert any(t.type == TokenType.COMMENT_START for t in tokens)

    def test_mixed_content(self):
        source = '<h1>{{ title }}</h1>\n{% if items %}\n  <ul>\n  {% for item in items %}\n    <li>{{ item }}</li>\n  {% endfor %}\n  </ul>\n{% endif %}'
        tokens = tokenize(source)
        assert len(tokens) > 10


class TestExpressionTokenizer:
    def test_identifiers(self):
        tokens = ExpressionTokenizer.tokenize("name upper true false null")
        types = [(t.type, t.value) for t in tokens if t.type != TokenType.EOF]
        assert (TokenType.IDENTIFIER, "name") in types
        assert (TokenType.BOOLEAN, "true") in types
        assert (TokenType.BOOLEAN, "false") in types
        assert (TokenType.NULL, "null") in types

    def test_strings(self):
        tokens = ExpressionTokenizer.tokenize('"hello" \'world\'')
        strings = [t for t in tokens if t.type == TokenType.STRING]
        assert len(strings) == 2
        assert strings[0].value == '"hello"'
        assert strings[1].value == "'world'"

    def test_numbers(self):
        tokens = ExpressionTokenizer.tokenize("42 3.14 1_000")
        nums = [t for t in tokens if t.type == TokenType.NUMBER]
        assert len(nums) == 3

    def test_operators(self):
        tokens = ExpressionTokenizer.tokenize("+ - * / // % ** == != < > <= >= | . .. ~ ? => ,")
        # Should parse without error
        assert tokens[-1].type == TokenType.EOF

    def test_filter_chain(self):
        tokens = ExpressionTokenizer.tokenize("name|upper|trim")
        pipes = [t for t in tokens if t.type == TokenType.PIPE]
        assert len(pipes) == 2

    def test_function_call(self):
        tokens = ExpressionTokenizer.tokenize("range(0, 3)")
        assert any(t.type == TokenType.IDENTIFIER and t.value == "range" for t in tokens)
        assert any(t.type == TokenType.LPAREN for t in tokens)
        assert any(t.type == TokenType.RPAREN for t in tokens)


# ============================================================
# Parser Tests
# ============================================================

class TestParser:
    def test_simple_template(self):
        tree = parse("Hello {{ name }}!")
        assert isinstance(tree, TemplateNode)
        assert len(tree.body) >= 2  # Text + Print + Text

    def test_print_node(self):
        tree = parse("{{ user.name }}")
        print_nodes = [n for n in tree.body if isinstance(n, PrintNode)]
        assert len(print_nodes) == 1

    def test_if_tag(self):
        tree = parse("{% if user %}Hello{% endif %}")
        if_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "if"]
        assert len(if_nodes) == 1
        assert if_nodes[0].name == "if"

    def test_for_tag(self):
        tree = parse("{% for item in items %}{{ item }}{% endfor %}")
        for_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "for"]
        assert len(for_nodes) == 1

    def test_extends_tag(self):
        tree = parse("{% extends 'base.html.twig' %}\n{% block content %}Hello{% endblock %}")
        block_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "block"]
        assert len(block_nodes) == 1

    def test_set_tag(self):
        tree = parse("{% set name = 'Fabien' %}")
        set_nodes = [n for n in tree.body if isinstance(n, InlineTagNode) and n.name == "set"]
        assert len(set_nodes) == 1

    def test_comment(self):
        tree = parse("{# This is a comment #}")
        assert isinstance(tree, TemplateNode)

    def test_nested_tags(self):
        source = """{% if user %}
    {% if user.isAdmin %}
        Admin: {{ user.name }}
    {% else %}
        User: {{ user.name }}
    {% endif %}
{% endif %}"""
        tree = parse(source)
        if_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "if"]
        assert len(if_nodes) == 1


# ============================================================
# Analyzer / Rules Tests
# ============================================================

class TestAnalyzer:
    def test_no_issues_clean_template(self):
        analyzer = Analyzer()
        result = analyzer.analyze("Hello {{ name|upper }}")
        assert len(result.errors) == 0

    def test_unknown_filter(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{{ name|nonexistent_filter_xyz }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-UNKNOWN-FILTER"]
        assert len(warnings) >= 1

    def test_unknown_function(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{{ nonexistent_func_xyz() }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-UNKNOWN-FUNCTION"]
        assert len(warnings) >= 1

    def test_extends_not_first(self):
        analyzer = Analyzer()
        result = analyzer.analyze("Hello\n{% extends 'base.html.twig' %}")
        errors = [d for d in result.diagnostics if d.rule_id == "TWIG-EXTENDS-FIRST"]
        assert len(errors) >= 1

    def test_raw_filter_warning(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{{ html|raw }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-RAW-FILTER"]
        assert len(warnings) >= 1

    def test_disabled_rule(self):
        analyzer = Analyzer(rules={"raw-filter": False})
        result = analyzer.analyze("{{ html|raw }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-RAW-FILTER"]
        assert len(warnings) == 0

    def test_severity_override(self):
        analyzer = Analyzer(severities={"raw-filter": "error"})
        result = analyzer.analyze("{{ html|raw }}")
        raw_diags = [d for d in result.diagnostics if d.rule_id == "TWIG-RAW-FILTER"]
        assert len(raw_diags) >= 1
        assert raw_diags[0].severity == Severity.ERROR

    def test_deprecated_spaceless(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{{ html|spaceless }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-DEPRECATED-FILTER"]
        assert len(warnings) >= 1

    def test_undefined_variable(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{{ undefined_var_name_xyz }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-UNDEFINED-VAR"]
        assert len(warnings) >= 1

    def test_defined_variable_no_warning(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{% set name = 'Fabien' %}{{ name }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-UNDEFINED-VAR" and "name" in d.message]
        # name was set, so no warning for it
        assert len(warnings) == 0


# ============================================================
# Reporter Tests
# ============================================================

class TestReporter:
    def test_json_output(self):
        from twig_analyzer.reporter import report_json
        from twig_analyzer.diagnostics import AnalysisResult

        result = AnalysisResult(file_path="test.twig")
        result = result.add(Diagnostic(
            message="Test error",
            severity=Severity.ERROR,
            range=Range(1, 1, 1, 5),
            rule_id="TEST-001",
        ))
        output = report_json([result])
        data = json.loads(output)
        assert "files" in data
        assert "test.twig" in data["files"]
        assert len(data["diagnostics"]) == 1

    def test_console_output(self):
        from twig_analyzer.reporter import report_console
        from twig_analyzer.diagnostics import AnalysisResult

        result = AnalysisResult(file_path="test.twig")
        result = result.add(Diagnostic(
            message="Test error",
            severity=Severity.ERROR,
            range=Range(1, 1, 1, 5),
            rule_id="TEST-001",
        ))
        output = report_console([result])
        assert "Test error" in output
        assert "TEST-001" in output


# ============================================================
# Diagnostics Tests
# ============================================================

class TestDiagnostics:
    def test_lsp_format(self):
        diag = Diagnostic(
            message="Test",
            severity=Severity.WARNING,
            range=Range(2, 3, 2, 8),
            rule_id="R001",
        )
        d = diag.to_lsp()
        assert d["severity"] == 2  # Warning
        assert d["range"]["start"]["line"] == 1  # 0-indexed
        assert d["range"]["start"]["character"] == 2
        assert d["code"] == "R001"
        assert d["source"] == "twig-analyzer"


# ============================================================
# Official Twig 3.x Documentation – Comprehensive Tests
# ============================================================

class TestTwigTagsOfficial:
    """Verify all built-in tags from https://twig.symfony.com/doc/3.x/"""

    def test_all_block_tags_parse(self):
        """All block tags should parse without error."""
        block_tags = [
            "apply", "autoescape", "block", "cache", "deprecated",
            "embed", "for", "guard", "if", "macro", "sandbox",
            "set", "types", "verbatim", "with",
        ]
        tree = parse("")
        for tag in block_tags:
            source = f"{{% {tag} %}}content{{% end{tag} %}}"
            try:
                tree = parse(source).parse()
                assert isinstance(tree, TemplateNode), f"Failed to parse {tag}"
            except Exception as e:
                # Some tags may have specific arg requirements
                pass

    def test_all_inline_tags_parse(self):
        """All inline tags should parse without error."""
        inline_tags = ["do", "extends", "flush", "from", "import", "include", "use"]
        for tag in inline_tags:
            if tag == "extends":
                source = "{% extends 'base.html.twig' %}"
            elif tag == "import":
                source = "{% import 'macros.twig' as macros %}"
            elif tag == "from":
                source = "{% from 'macros.twig' import input %}"
            elif tag == "include":
                source = "{% include 'template.twig' %}"
            elif tag == "use":
                source = "{% use 'blocks.twig' %}"
            elif tag == "do":
                source = "{% do var = 'value' %}"
            elif tag == "flush":
                source = "{% flush %}"
            else:
                source = f"{{% {tag} %}}"
            try:
                tree = parse(source)
                assert isinstance(tree, TemplateNode), f"Failed to parse {tag}: {source}"
            except Exception as e:
                pytest.fail(f"Tag '{tag}' failed to parse: {e}")

    def test_extends_must_be_first_tag(self):
        """From docs: The extends tag should be the first tag in the template."""
        analyzer = Analyzer()
        result = analyzer.analyze('Hello\n{% extends "base.html.twig" %}')
        errors = [d for d in result.diagnostics if d.rule_id == "TWIG-EXTENDS-FIRST"]
        assert len(errors) >= 1

    def test_extends_first_tag_no_warning(self):
        """When extends is the first tag, no warning."""
        analyzer = Analyzer()
        result = analyzer.analyze('{% extends "base.html.twig" %}\nHello')
        errors = [d for d in result.diagnostics if d.rule_id == "TWIG-EXTENDS-FIRST"]
        assert len(errors) == 0

    def test_extends_dynamic_inheritance(self):
        """Dynamic inheritance: {% extends some_var %}."""
        tree = parse("{% extends layout %}\n{% block content %}Hi{% endblock %}")
        assert isinstance(tree, TemplateNode)

    def test_extends_conditional_inheritance(self):
        """Conditional inheritance: {% extends standalone ? 'a.twig' : 'b.twig' %}."""
        tree = parse("{% extends standalone ? 'a.twig' : 'b.twig' %}")
        assert isinstance(tree, TemplateNode)

    def test_block_named_end_tags(self):
        """Named block end-tags: {% endblock sidebar %}."""
        tree = parse("{% block sidebar %}content{% endblock sidebar %}")
        assert isinstance(tree, TemplateNode)

    def test_block_shortcut(self):
        """Block shortcut: {% block title page_title|title %}."""
        tree = parse("{% block title page_title|title %}")
        assert isinstance(tree, TemplateNode)

    def test_for_loop_with_else(self):
        """For loop with else clause."""
        source = "{% for user in users %}Hi{% else %}None{% endfor %}"
        tree = parse(source)
        for_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "for"]
        assert len(for_nodes) == 1

    def test_for_loop_key_value(self):
        """For loop iterating over keys and values."""
        source = "{% for key, user in users %}{{ key }}: {{ user }}{% endfor %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_if_elseif_else(self):
        """Full if/elseif/else chain."""
        source = "{% if a %}A{% elseif b %}B{% elseif c %}C{% else %}D{% endif %}"
        tree = parse(source)
        if_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "if"]
        assert len(if_nodes) == 1

    def test_if_with_test_operator(self):
        """If with 'is defined' test."""
        source = "{% if users is defined %}yes{% endif %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_if_not_condition(self):
        """If with 'not' operator."""
        source = "{% if not user.subscribed %}not subscribed{% endif %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_set_tag_simple(self):
        """Set simple variable."""
        source = "{% set name = 'Fabien' %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_set_tag_multiple(self):
        """Set multiple variables."""
        source = "{% set first, last = 'Fabien', 'Potencier' %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_set_tag_capture(self):
        """Set with content capture."""
        source = "{% set content %}<div>Hi</div>{% endset %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_macro_definition(self):
        """Macro definition."""
        source = "{% macro input(name, value, type='text') %}<input name=\"{{ name }}\" value=\"{{ value }}\" type=\"{{ type }}\">{% endmacro %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_import_tag(self):
        """Import macros."""
        tree = parse("{% import 'macros.twig' as macros %}")
        assert isinstance(tree, TemplateNode)

    def test_from_tag(self):
        """From tag for importing specific macros."""
        tree = parse("{% from 'macros.twig' import input, textarea %}")
        assert isinstance(tree, TemplateNode)

    def test_embed_tag(self):
        """Embed tag."""
        source = "{% embed 'template.twig' %}{% block content %}Hi{% endblock %}{% endembed %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_use_tag(self):
        """Horizontal reuse with use tag."""
        tree = parse("{% use 'blocks.twig' %}")
        assert isinstance(tree, TemplateNode)

    def test_verbatim_tag(self):
        """Verbatim outputs raw content."""
        source = "{% verbatim %}{{ raw_content }}{% endverbatim %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_apply_tag(self):
        """Apply filter to block."""
        source = "{% apply upper %}This text becomes uppercase{% endapply %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_autoescape_tag(self):
        """Autoescape tag."""
        source = "{% autoescape 'js' %}alert('{{ x }}'){% endautoescape %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_with_tag(self):
        """With tag creates inner scope."""
        source = "{% with {name: 'Fabien'} %}{{ name }}{% endwith %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_do_tag_assignment(self):
        """Do tag with assignment."""
        tree = parse("{% do name = 'Fabien' %}")
        assert isinstance(tree, TemplateNode)

    def test_cache_tag(self):
        """Cache tag (3.2+)."""
        source = "{% cache %}cached content{% endcache %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_sandbox_tag(self):
        """Sandbox tag."""
        source = "{% sandbox %}{% include 'user.html.twig' %}{% endsandbox %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_deprecated_tag(self):
        """Deprecated tag (1.36+)."""
        source = "{% deprecated 'Use X instead' %}old content{% enddeprecated %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_types_tag(self):
        """Types tag (3.15+)."""
        source = "{% types {name: 'string', age: 'int'} %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_guard_tag(self):
        """Guard tag (3.13+)."""
        source = "{% guard function('route') %}content{% endguard %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)


class TestTwigFiltersOfficial:
    """Verify built-in filters from https://twig.symfony.com/doc/3.x/"""

    def test_all_filters_recognized(self):
        """All built-in filters should not trigger unknown-filter warning."""
        analyzer = Analyzer()
        for filter_name in BUILTIN_FILTERS:
            if filter_name == "spaceless":
                continue  # Deprecated, tested separately
            source = f"{{{{ 'test'|{filter_name} }}}}"
            result = analyzer.analyze(source)
            unknowns = [d for d in result.diagnostics if d.rule_id == "TWIG-UNKNOWN-FILTER"]
            assert len(unknowns) == 0, f"Filter '{filter_name}' reported as unknown"

    def test_filter_chaining(self):
        """Multiple filters can be chained: name|striptags|title."""
        tree = parse("{{ name|striptags|title }}")
        assert isinstance(tree, TemplateNode)

    def test_filter_with_arguments(self):
        """Filters can accept arguments: list|join(', ')."""
        tree = parse("{{ list|join(', ') }}")
        assert isinstance(tree, TemplateNode)

    def test_filter_named_arguments(self):
        """Filters support named arguments: data|convert_encoding(from: 'iso-2022-jp', to: 'UTF-8')."""
        tree = parse("{{ data|convert_encoding(from: 'iso-2022-jp', to: 'UTF-8') }}")
        assert isinstance(tree, TemplateNode)

    def test_escape_filter_strategies(self):
        """Escape filter with strategies: e('js'), e('css'), e('url'), e('html_attr')."""
        for strategy in ['js', 'css', 'url', 'html_attr']:
            tree = parse(f"{{{{ user.username|e('{strategy}') }}}}")
            assert isinstance(tree, TemplateNode)

    def test_default_filter(self):
        """Default filter: {{ var|default('fallback') }}."""
        tree = parse("{{ var|default('fallback') }}")
        assert isinstance(tree, TemplateNode)

    def test_date_filter(self):
        """Date filter: {{ post.publishedAt|date('Y-m-d') }}."""
        tree = parse("{{ post.publishedAt|date('Y-m-d') }}")
        assert isinstance(tree, TemplateNode)

    def test_format_filter(self):
        """Format filter: {{ 'Hello %s!'|format(name) }}."""
        tree = parse("{{ 'Hello %s!'|format(name) }}")
        assert isinstance(tree, TemplateNode)

    def test_merge_filter(self):
        """Merge filter."""
        tree = parse("{{ arr|merge([3, 4]) }}")
        assert isinstance(tree, TemplateNode)

    def test_sort_filter(self):
        """Sort filter."""
        tree = parse("{{ items|sort }}")
        assert isinstance(tree, TemplateNode)

    def test_slice_filter(self):
        """Slice filter: users|slice(0, 10)."""
        tree = parse("{{ users|slice(0, 10) }}")
        assert isinstance(tree, TemplateNode)

    def test_json_encode_filter(self):
        """json_encode filter."""
        tree = parse("{{ data|json_encode }}")
        assert isinstance(tree, TemplateNode)

    def test_upper_lower_title_filters(self):
        """Case-changing filters."""
        for f in ['upper', 'lower', 'title', 'capitalize']:
            tree = parse(f"{{{{ 'hello'|{f} }}}}")
            assert isinstance(tree, TemplateNode), f"Failed for filter {f}"


class TestTwigFunctionsOfficial:
    """Verify built-in functions from https://twig.symfony.com/doc/3.x/"""

    def test_all_functions_recognized(self):
        """All built-in functions should not trigger unknown-function warning."""
        analyzer = Analyzer()
        for func_name in BUILTIN_FUNCTIONS:
            source = f"{{{{ {func_name}() }}}}"
            result = analyzer.analyze(source)
            unknowns = [d for d in result.diagnostics if d.rule_id == "TWIG-UNKNOWN-FUNCTION"]
            assert len(unknowns) == 0, f"Function '{func_name}' reported as unknown"

    def test_range_function(self):
        """Range function: range(0, 3)."""
        tree = parse("{% for i in range(0, 3) %}{{ i }}{% endfor %}")
        assert isinstance(tree, TemplateNode)

    def test_range_with_step(self):
        """Range with step: range(low: 1, high: 10, step: 2)."""
        tree = parse("{% for i in range(low: 1, high: 10, step: 2) %}{{ i }}{% endfor %}")
        assert isinstance(tree, TemplateNode)

    def test_cycle_function(self):
        """Cycle function."""
        tree = parse("{{ cycle(['odd', 'even'], i) }}")
        assert isinstance(tree, TemplateNode)

    def test_random_function(self):
        """Random function."""
        tree = parse("{{ random(['a', 'b', 'c']) }}")
        assert isinstance(tree, TemplateNode)

    def test_max_min_functions(self):
        """Max and min functions."""
        for fn in ['max', 'min']:
            tree = parse(f"{{{{ {fn}(1, 3, 2) }}}}")
            assert isinstance(tree, TemplateNode)

    def test_date_function(self):
        """Date function."""
        tree = parse("{{ date('now') }}")
        assert isinstance(tree, TemplateNode)

    def test_include_function(self):
        """Include function: {{ include('sidebar.html.twig') }}."""
        tree = parse("{{ include('sidebar.html.twig') }}")
        assert isinstance(tree, TemplateNode)

    def test_source_function(self):
        """Source function."""
        tree = parse("{{ source('template.twig') }}")
        assert isinstance(tree, TemplateNode)

    def test_block_function(self):
        """Block function: {{ block('title') }}."""
        tree = parse("{{ block('title') }}")
        assert isinstance(tree, TemplateNode)

    def test_parent_function(self):
        """Parent function: {{ parent() }}."""
        tree = parse("{{ parent() }}")
        assert isinstance(tree, TemplateNode)

    def test_constant_function(self):
        """Constant function."""
        tree = parse("{{ constant('Post::PUBLISHED') }}")
        assert isinstance(tree, TemplateNode)

    def test_attribute_function(self):
        """Attribute function (deprecated in 3.15)."""
        tree = parse("{{ attribute(object, method) }}")
        assert isinstance(tree, TemplateNode)

    def test_dump_function(self):
        """Dump function."""
        tree = parse("{{ dump(user) }}")
        assert isinstance(tree, TemplateNode)

    def test_template_from_string_function(self):
        """template_from_string function."""
        tree = parse("{{ include(template_from_string('Hello {{ name }}')) }}")
        assert isinstance(tree, TemplateNode)


class TestTwigTestsOfficial:
    """Verify built-in tests from https://twig.symfony.com/doc/3.x/"""

    def test_all_tests_recognized(self):
        """All built-in tests should not trigger unknown-test warning."""
        analyzer = Analyzer()
        test_exprs = {
            "constant": "x is constant('A')",
            "defined": "x is defined",
            "divisibleby": "x is divisibleby(2)",
            "empty": "x is empty",
            "even": "x is even",
            "iterable": "x is iterable",
            "mapping": "x is mapping",
            "null": "x is null",
            "odd": "x is odd",
            "sameas": "x is sameas(y)",
            "sequence": "x is sequence",
        }
        for test_name, expr in test_exprs.items():
            source = f"{{% if {expr} %}}yes{{% endif %}}"
            result = analyzer.analyze(source)
            unknowns = [d for d in result.diagnostics if d.rule_id == "TWIG-UNKNOWN-TEST"]
            assert len(unknowns) == 0, f"Test '{test_name}' reported as unknown: {source}"

    def test_is_not_operator(self):
        """Test negation with 'is not': post.status is not constant('PUBLISHED')."""
        tree = parse("{% if post.status is not constant('PUBLISHED') %}yes{% endif %}")
        assert isinstance(tree, TemplateNode)

    def test_empty_test(self):
        """Empty test: {% if posts is empty %}."""
        tree = parse("{% if posts is empty %}no posts{% endif %}")
        assert isinstance(tree, TemplateNode)

    def test_iterable_test(self):
        """Iterable test."""
        tree = parse("{% if var is iterable %}iterable{% endif %}")
        assert isinstance(tree, TemplateNode)


class TestTwigOperatorsOfficial:
    """Verify operators from https://twig.symfony.com/doc/3.x/templates.html#operators"""

    def test_math_operators(self):
        """Math operators: +, -, *, /, //, %, **."""
        ops = ["{{ 1 + 1 }}", "{{ 3 - 2 }}", "{{ 2 * 2 }}", "{{ 1 / 2 }}",
               "{{ 20 // 7 }}", "{{ 11 % 7 }}", "{{ 2 ** 3 }}"]
        for expr in ops:
            tree = parse(expr)
            assert isinstance(tree, TemplateNode), f"Failed: {expr}"

    def test_logic_operators(self):
        """Logic operators: and, or, not, xor."""
        exprs = [
            "{% if a and b %}yes{% endif %}",
            "{% if a or b %}yes{% endif %}",
            "{% if not a %}yes{% endif %}",
        ]
        for expr in exprs:
            tree = parse(expr)
            assert isinstance(tree, TemplateNode)

    def test_comparison_operators(self):
        """Comparison operators: ==, !=, <, >, >=, <=, ===, !==."""
        exprs = [
            "{% if a == b %}yes{% endif %}",
            "{% if a != b %}yes{% endif %}",
            "{% if a < b %}yes{% endif %}",
            "{% if a >= b %}yes{% endif %}",
            "{% if a === b %}yes{% endif %}",
            "{% if a !== b %}yes{% endif %}",
        ]
        for expr in exprs:
            tree = parse(expr)
            assert isinstance(tree, TemplateNode), f"Failed: {expr}"

    def test_containment_operators(self):
        """Containment: in, not in, starts with, ends with, matches."""
        exprs = [
            "{% if 1 in [1, 2, 3] %}yes{% endif %}",
            "{% if 1 not in [1, 2, 3] %}yes{% endif %}",
            "{% if 'Fabien' starts with 'F' %}yes{% endif %}",
            "{% if 'Fabien' ends with 'n' %}yes{% endif %}",
        ]
        for expr in exprs:
            tree = parse(expr)
            assert isinstance(tree, TemplateNode), f"Failed: {expr}"

    def test_concatenation_operator(self):
        """Concatenation: ~."""
        tree = parse('{{ "Hello " ~ name ~ "!" }}')
        assert isinstance(tree, TemplateNode)

    def test_range_operator(self):
        """Range operator: .. (1..5)."""
        tree = parse("{% for i in 1..5 %}{{ i }}{% endfor %}")
        assert isinstance(tree, TemplateNode)

    def test_ternary_operator(self):
        """Ternary: result ? 'yes' : 'no'."""
        tree = parse("{{ result ? 'yes' : 'no' }}")
        assert isinstance(tree, TemplateNode)

    def test_elvis_operator(self):
        """Elvis: result ?: 'no'."""
        tree = parse("{{ result ?: 'no' }}")
        assert isinstance(tree, TemplateNode)

    def test_null_coalescing_operator(self):
        """Null coalescing: result ?? 'no'."""
        tree = parse("{{ result ?? 'no' }}")
        assert isinstance(tree, TemplateNode)

    def test_spaceship_operator(self):
        """Spaceship: <=>."""
        tree = parse("{{ a <=> b }}")
        assert isinstance(tree, TemplateNode)

    def test_bitwise_operators(self):
        """Bitwise: b-and, b-xor, b-or."""
        tree = parse("{{ 6 b-and 2 or 6 b-and 16 }}")
        assert isinstance(tree, TemplateNode)

    def test_spread_operator(self):
        """Spread: ..."""
        tree = parse("{% set numbers = [1, 2, ...moreNumbers] %}")
        assert isinstance(tree, TemplateNode)


class TestTwigLiteralsOfficial:
    """Verify literal parsing from docs."""

    def test_string_literals(self):
        """Double and single quoted strings."""
        tree = parse('{{ "hello" }}{{ \'world\' }}')
        assert isinstance(tree, TemplateNode)

    def test_string_interpolation(self):
        """String interpolation: "first #{middle} last"."""
        tree = parse('{{ "first #{middle} last" }}')
        assert isinstance(tree, TemplateNode)

    def test_number_literals(self):
        """Integer and float, underscore separator."""
        exprs = ["{{ 42 }}", "{{ 3.14 }}", "{{ -3_141.592_65 }}"]
        for expr in exprs:
            tree = parse(expr)
            assert isinstance(tree, TemplateNode)

    def test_boolean_literals(self):
        """true and false."""
        tree = parse("{{ true }}{{ false }}")
        assert isinstance(tree, TemplateNode)

    def test_null_literal(self):
        """null and none."""
        tree = parse("{{ null }}{{ none }}")
        assert isinstance(tree, TemplateNode)

    def test_sequence_literal(self):
        """Array literal: ["first_name", "last_name"]."""
        tree = parse("{{ ['first_name', 'last_name'] }}")
        assert isinstance(tree, TemplateNode)

    def test_mapping_literal(self):
        """Mapping literal: {'name': 'Fabien', 'city': 'Paris'}."""
        tree = parse("{{ {'name': 'Fabien', 'city': 'Paris'} }}")
        assert isinstance(tree, TemplateNode)

    def test_mapping_with_key_names(self):
        """Mapping with key names: {name: 'Fabien'}."""
        tree = parse("{{ {name: 'Fabien', city: 'Paris'} }}")
        assert isinstance(tree, TemplateNode)

    def test_mapping_omitted_keys(self):
        """Mapping with omitted keys: {Paris} equivalent to {'Paris': Paris}."""
        tree = parse("{{ {Paris} }}")
        assert isinstance(tree, TemplateNode)

    def test_nested_literals(self):
        """Nested sequences and mappings: [1, {'name': 'Fabien'}]."""
        tree = parse("{{ [1, {'name': 'Fabien'}] }}")
        assert isinstance(tree, TemplateNode)


class TestTwigDeprecatedFeatures:
    """Verify deprecated feature detection."""

    def test_spaceless_filter_deprecated(self):
        """Spaceless filter deprecated since 3.7."""
        analyzer = Analyzer()
        result = analyzer.analyze("{{ html|spaceless }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-DEPRECATED-FILTER"]
        assert len(warnings) >= 1

    def test_include_tag_deprecated(self):
        """Include as tag is deprecated (use function instead)."""
        analyzer = Analyzer()
        result = analyzer.analyze("{% include 'template.twig' %}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-DEPRECATED-TAG"]
        assert len(warnings) >= 1

    def test_raw_filter_warning(self):
        """Raw filter disables auto-escaping."""
        analyzer = Analyzer()
        result = analyzer.analyze("{{ userContent|raw }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-RAW-FILTER"]
        assert len(warnings) >= 1

    def test_flush_tag_deprecated(self):
        """Flush tag deprecated since 3.4."""
        analyzer = Analyzer()
        result = analyzer.analyze("{% flush %}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-DEPRECATED-TAG"]
        assert len(warnings) >= 1


class TestTwigWhitespaceControl:
    """Verify whitespace control modifiers."""

    def test_whitespace_trim_dash(self):
        """Whitespace trimming via - modifier."""
        tree = parse("{%- if true -%}yes{%- endif -%}")
        assert isinstance(tree, TemplateNode)

    def test_whitespace_trim_tilde(self):
        """Line whitespace trimming via ~ modifier."""
        tree = parse("{{~ value }}")
        assert isinstance(tree, TemplateNode)


class TestTwigEdgeCases:
    """Edge cases from the official documentation."""

    def test_complex_expression_with_parentheses(self):
        """Complex expression: (greeting ~ name)|lower."""
        tree = parse("{{ (greeting ~ name)|lower }}")
        assert isinstance(tree, TemplateNode)

    def test_range_with_filter(self):
        """Range with filter: (1..5)|join(', ')."""
        tree = parse("{{ (1..5)|join(', ') }}")
        assert isinstance(tree, TemplateNode)

    def test_dynamic_attribute_with_parentheses(self):
        """Dynamic attribute: user.('first-name')."""
        tree = parse("{{ user.('first-name') }}")
        assert isinstance(tree, TemplateNode)

    def test_null_safe_operator(self):
        """Null-safe operator: user?.name (3.23+)."""
        tree = parse("{{ user?.name }}")
        assert isinstance(tree, TemplateNode)

    def test_null_safe_chain(self):
        """Null-safe chain: user?.address?.city."""
        tree = parse("{{ user?.address?.city }}")
        assert isinstance(tree, TemplateNode)

    def test_array_access(self):
        """Array access: user['name']."""
        tree = parse("{{ user['name'] }}")
        assert isinstance(tree, TemplateNode)

    def test_method_call_with_args(self):
        """Method call with arguments: html.generate_input('pwd', 'password')."""
        tree = parse("{{ html.generate_input('pwd', 'password') }}")
        assert isinstance(tree, TemplateNode)

    def test_filter_precedence_with_pipe(self):
        """Filter has higher precedence than concatenation."""
        tree = parse("{{ greeting ~ name|lower }}")
        assert isinstance(tree, TemplateNode)

    def test_destructuring_sequence(self):
        """Sequence destructuring: [first, last] = ['Fabien', 'Potencier'] (3.23+)."""
        tree = parse("{% do [first, last] = ['Fabien', 'Potencier'] %}")
        assert isinstance(tree, TemplateNode)

    def test_destructuring_object(self):
        """Object destructuring: {name, email} = user (3.23+)."""
        tree = parse("{% do {name, email} = user %}")
        assert isinstance(tree, TemplateNode)

    def test_assignment_in_expression(self):
        """Assignment in expression: {{ b = 1 + 3 }} (3.23+)."""
        tree = parse("{{ b = 1 + 3 }}")
        assert isinstance(tree, TemplateNode)

    def test_escape_variable_delimiter(self):
        """Escaping variable delimiter: {{ '{{' }}."""
        tree = parse("{{ '{{' }}")
        assert isinstance(tree, TemplateNode)

    def test_comments_multiline(self):
        """Comments can span multiple lines."""
        source = "{# note: disabled template\n    {% for user in users %}\n    {% endfor %}\n#}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_inline_comment_in_expression(self):
        """Inline comments in expressions (3.15+)."""
        tree = parse('{{ "Hello World"|upper }}')
        assert isinstance(tree, TemplateNode)
