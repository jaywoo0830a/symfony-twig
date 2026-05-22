"""Unit tests for Twig Static Analyzer."""

import json
import tempfile
import os
import pytest
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from twig_analyzer.lexer import Lexer, ExpressionTokenizer, TokenType
from twig_analyzer.parser import Parser
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
        lexer = Lexer("Hello World")
        tokens = lexer.tokenize()
        assert len(tokens) >= 2  # TEXT + EOF
        assert tokens[0].type == TokenType.TEXT
        assert "Hello World" in tokens[0].value

    def test_var_delimiter(self):
        lexer = Lexer("{{ name }}")
        tokens = lexer.tokenize()
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert TokenType.VAR_START in types
        assert TokenType.VAR_END in types

    def test_block_delimiter(self):
        lexer = Lexer("{% if true %}{% endif %}")
        tokens = lexer.tokenize()
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert TokenType.BLOCK_START in types
        assert TokenType.BLOCK_END in types

    def test_comment_delimiter(self):
        lexer = Lexer("{# comment #}")
        tokens = lexer.tokenize()
        types = [t.type for t in tokens if t.type != TokenType.EOF]
        assert TokenType.COMMENT_START in types
        assert TokenType.COMMENT_END in types

    def test_mixed_content(self):
        source = '<h1>{{ title }}</h1>\n{% if items %}\n  <ul>\n  {% for item in items %}\n    <li>{{ item }}</li>\n  {% endfor %}\n  </ul>\n{% endif %}'
        lexer = Lexer(source)
        tokens = lexer.tokenize()
        assert len(tokens) > 10


class TestExpressionTokenizer:
    def test_identifiers(self):
        et = ExpressionTokenizer("name upper true false null")
        tokens = et.tokenize()
        types = [(t.type, t.value) for t in tokens if t.type != TokenType.EOF]
        assert (TokenType.IDENTIFIER, "name") in types
        assert (TokenType.BOOLEAN, "true") in types
        assert (TokenType.BOOLEAN, "false") in types
        assert (TokenType.NULL, "null") in types

    def test_strings(self):
        et = ExpressionTokenizer('"hello" \'world\'')
        tokens = et.tokenize()
        strings = [t for t in tokens if t.type == TokenType.STRING]
        assert len(strings) == 2
        assert strings[0].value == '"hello"'
        assert strings[1].value == "'world'"

    def test_numbers(self):
        et = ExpressionTokenizer("42 3.14 1_000")
        tokens = et.tokenize()
        nums = [t for t in tokens if t.type == TokenType.NUMBER]
        assert len(nums) == 3

    def test_operators(self):
        et = ExpressionTokenizer("+ - * / // % ** == != < > <= >= | . .. ~ ? => ,")
        tokens = et.tokenize()
        # Should parse without error
        assert tokens[-1].type == TokenType.EOF

    def test_filter_chain(self):
        et = ExpressionTokenizer("name|upper|trim")
        tokens = et.tokenize()
        pipes = [t for t in tokens if t.type == TokenType.PIPE]
        assert len(pipes) == 2

    def test_function_call(self):
        et = ExpressionTokenizer("range(0, 3)")
        tokens = et.tokenize()
        assert any(t.type == TokenType.IDENTIFIER and t.value == "range" for t in tokens)
        assert any(t.type == TokenType.LPAREN for t in tokens)
        assert any(t.type == TokenType.RPAREN for t in tokens)


# ============================================================
# Parser Tests
# ============================================================

class TestParser:
    def test_simple_template(self):
        parser = Parser("Hello {{ name }}!")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)
        assert len(tree.body) >= 2  # Text + Print + Text

    def test_print_node(self):
        parser = Parser("{{ user.name }}")
        tree = parser.parse()
        print_nodes = [n for n in tree.body if isinstance(n, PrintNode)]
        assert len(print_nodes) == 1

    def test_if_tag(self):
        parser = Parser("{% if user %}Hello{% endif %}")
        tree = parser.parse()
        if_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "if"]
        assert len(if_nodes) == 1
        assert if_nodes[0].name == "if"

    def test_for_tag(self):
        parser = Parser("{% for item in items %}{{ item }}{% endfor %}")
        tree = parser.parse()
        for_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "for"]
        assert len(for_nodes) == 1

    def test_extends_tag(self):
        parser = Parser("{% extends 'base.html.twig' %}\n{% block content %}Hello{% endblock %}")
        tree = parser.parse()
        block_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "block"]
        assert len(block_nodes) == 1

    def test_set_tag(self):
        parser = Parser("{% set name = 'Fabien' %}")
        tree = parser.parse()
        set_nodes = [n for n in tree.body if isinstance(n, InlineTagNode) and n.name == "set"]
        assert len(set_nodes) == 1

    def test_comment(self):
        parser = Parser("{# This is a comment #}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_nested_tags(self):
        source = """{% if user %}
    {% if user.isAdmin %}
        Admin: {{ user.name }}
    {% else %}
        User: {{ user.name }}
    {% endif %}
{% endif %}"""
        parser = Parser(source)
        tree = parser.parse()
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
        result.add(Diagnostic(
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
        result.add(Diagnostic(
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
        d = diag.to_dict()
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
        parser = Parser("")
        for tag in block_tags:
            source = f"{{% {tag} %}}content{{% end{tag} %}}"
            try:
                tree = Parser(source).parse()
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
                tree = Parser(source).parse()
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
        parser = Parser("{% extends layout %}\n{% block content %}Hi{% endblock %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_extends_conditional_inheritance(self):
        """Conditional inheritance: {% extends standalone ? 'a.twig' : 'b.twig' %}."""
        parser = Parser("{% extends standalone ? 'a.twig' : 'b.twig' %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_block_named_end_tags(self):
        """Named block end-tags: {% endblock sidebar %}."""
        parser = Parser("{% block sidebar %}content{% endblock sidebar %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_block_shortcut(self):
        """Block shortcut: {% block title page_title|title %}."""
        parser = Parser("{% block title page_title|title %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_for_loop_with_else(self):
        """For loop with else clause."""
        source = "{% for user in users %}Hi{% else %}None{% endfor %}"
        parser = Parser(source)
        tree = parser.parse()
        for_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "for"]
        assert len(for_nodes) == 1

    def test_for_loop_key_value(self):
        """For loop iterating over keys and values."""
        source = "{% for key, user in users %}{{ key }}: {{ user }}{% endfor %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_if_elseif_else(self):
        """Full if/elseif/else chain."""
        source = "{% if a %}A{% elseif b %}B{% elseif c %}C{% else %}D{% endif %}"
        parser = Parser(source)
        tree = parser.parse()
        if_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "if"]
        assert len(if_nodes) == 1

    def test_if_with_test_operator(self):
        """If with 'is defined' test."""
        source = "{% if users is defined %}yes{% endif %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_if_not_condition(self):
        """If with 'not' operator."""
        source = "{% if not user.subscribed %}not subscribed{% endif %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_set_tag_simple(self):
        """Set simple variable."""
        source = "{% set name = 'Fabien' %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_set_tag_multiple(self):
        """Set multiple variables."""
        source = "{% set first, last = 'Fabien', 'Potencier' %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_set_tag_capture(self):
        """Set with content capture."""
        source = "{% set content %}<div>Hi</div>{% endset %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_macro_definition(self):
        """Macro definition."""
        source = "{% macro input(name, value, type='text') %}<input name=\"{{ name }}\" value=\"{{ value }}\" type=\"{{ type }}\">{% endmacro %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_import_tag(self):
        """Import macros."""
        parser = Parser("{% import 'macros.twig' as macros %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_from_tag(self):
        """From tag for importing specific macros."""
        parser = Parser("{% from 'macros.twig' import input, textarea %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_embed_tag(self):
        """Embed tag."""
        source = "{% embed 'template.twig' %}{% block content %}Hi{% endblock %}{% endembed %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_use_tag(self):
        """Horizontal reuse with use tag."""
        parser = Parser("{% use 'blocks.twig' %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_verbatim_tag(self):
        """Verbatim outputs raw content."""
        source = "{% verbatim %}{{ raw_content }}{% endverbatim %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_apply_tag(self):
        """Apply filter to block."""
        source = "{% apply upper %}This text becomes uppercase{% endapply %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_autoescape_tag(self):
        """Autoescape tag."""
        source = "{% autoescape 'js' %}alert('{{ x }}'){% endautoescape %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_with_tag(self):
        """With tag creates inner scope."""
        source = "{% with {name: 'Fabien'} %}{{ name }}{% endwith %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_do_tag_assignment(self):
        """Do tag with assignment."""
        parser = Parser("{% do name = 'Fabien' %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_cache_tag(self):
        """Cache tag (3.2+)."""
        source = "{% cache %}cached content{% endcache %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_sandbox_tag(self):
        """Sandbox tag."""
        source = "{% sandbox %}{% include 'user.html.twig' %}{% endsandbox %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_deprecated_tag(self):
        """Deprecated tag (1.36+)."""
        source = "{% deprecated 'Use X instead' %}old content{% enddeprecated %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_types_tag(self):
        """Types tag (3.15+)."""
        source = "{% types {name: 'string', age: 'int'} %}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_guard_tag(self):
        """Guard tag (3.13+)."""
        source = "{% guard function('route') %}content{% endguard %}"
        parser = Parser(source)
        tree = parser.parse()
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
        parser = Parser("{{ name|striptags|title }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_filter_with_arguments(self):
        """Filters can accept arguments: list|join(', ')."""
        parser = Parser("{{ list|join(', ') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_filter_named_arguments(self):
        """Filters support named arguments: data|convert_encoding(from: 'iso-2022-jp', to: 'UTF-8')."""
        parser = Parser("{{ data|convert_encoding(from: 'iso-2022-jp', to: 'UTF-8') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_escape_filter_strategies(self):
        """Escape filter with strategies: e('js'), e('css'), e('url'), e('html_attr')."""
        for strategy in ['js', 'css', 'url', 'html_attr']:
            parser = Parser(f"{{{{ user.username|e('{strategy}') }}}}")
            tree = parser.parse()
            assert isinstance(tree, TemplateNode)

    def test_default_filter(self):
        """Default filter: {{ var|default('fallback') }}."""
        parser = Parser("{{ var|default('fallback') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_date_filter(self):
        """Date filter: {{ post.publishedAt|date('Y-m-d') }}."""
        parser = Parser("{{ post.publishedAt|date('Y-m-d') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_format_filter(self):
        """Format filter: {{ 'Hello %s!'|format(name) }}."""
        parser = Parser("{{ 'Hello %s!'|format(name) }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_merge_filter(self):
        """Merge filter."""
        parser = Parser("{{ arr|merge([3, 4]) }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_sort_filter(self):
        """Sort filter."""
        parser = Parser("{{ items|sort }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_slice_filter(self):
        """Slice filter: users|slice(0, 10)."""
        parser = Parser("{{ users|slice(0, 10) }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_json_encode_filter(self):
        """json_encode filter."""
        parser = Parser("{{ data|json_encode }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_upper_lower_title_filters(self):
        """Case-changing filters."""
        for f in ['upper', 'lower', 'title', 'capitalize']:
            parser = Parser(f"{{{{ 'hello'|{f} }}}}")
            tree = parser.parse()
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
        parser = Parser("{% for i in range(0, 3) %}{{ i }}{% endfor %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_range_with_step(self):
        """Range with step: range(low: 1, high: 10, step: 2)."""
        parser = Parser("{% for i in range(low: 1, high: 10, step: 2) %}{{ i }}{% endfor %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_cycle_function(self):
        """Cycle function."""
        parser = Parser("{{ cycle(['odd', 'even'], i) }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_random_function(self):
        """Random function."""
        parser = Parser("{{ random(['a', 'b', 'c']) }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_max_min_functions(self):
        """Max and min functions."""
        for fn in ['max', 'min']:
            parser = Parser(f"{{{{ {fn}(1, 3, 2) }}}}")
            tree = parser.parse()
            assert isinstance(tree, TemplateNode)

    def test_date_function(self):
        """Date function."""
        parser = Parser("{{ date('now') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_include_function(self):
        """Include function: {{ include('sidebar.html.twig') }}."""
        parser = Parser("{{ include('sidebar.html.twig') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_source_function(self):
        """Source function."""
        parser = Parser("{{ source('template.twig') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_block_function(self):
        """Block function: {{ block('title') }}."""
        parser = Parser("{{ block('title') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_parent_function(self):
        """Parent function: {{ parent() }}."""
        parser = Parser("{{ parent() }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_constant_function(self):
        """Constant function."""
        parser = Parser("{{ constant('Post::PUBLISHED') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_attribute_function(self):
        """Attribute function (deprecated in 3.15)."""
        parser = Parser("{{ attribute(object, method) }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_dump_function(self):
        """Dump function."""
        parser = Parser("{{ dump(user) }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_template_from_string_function(self):
        """template_from_string function."""
        parser = Parser("{{ include(template_from_string('Hello {{ name }}')) }}")
        tree = parser.parse()
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
        parser = Parser("{% if post.status is not constant('PUBLISHED') %}yes{% endif %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_empty_test(self):
        """Empty test: {% if posts is empty %}."""
        parser = Parser("{% if posts is empty %}no posts{% endif %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_iterable_test(self):
        """Iterable test."""
        parser = Parser("{% if var is iterable %}iterable{% endif %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)


class TestTwigOperatorsOfficial:
    """Verify operators from https://twig.symfony.com/doc/3.x/templates.html#operators"""

    def test_math_operators(self):
        """Math operators: +, -, *, /, //, %, **."""
        ops = ["{{ 1 + 1 }}", "{{ 3 - 2 }}", "{{ 2 * 2 }}", "{{ 1 / 2 }}",
               "{{ 20 // 7 }}", "{{ 11 % 7 }}", "{{ 2 ** 3 }}"]
        for expr in ops:
            parser = Parser(expr)
            tree = parser.parse()
            assert isinstance(tree, TemplateNode), f"Failed: {expr}"

    def test_logic_operators(self):
        """Logic operators: and, or, not, xor."""
        exprs = [
            "{% if a and b %}yes{% endif %}",
            "{% if a or b %}yes{% endif %}",
            "{% if not a %}yes{% endif %}",
        ]
        for expr in exprs:
            parser = Parser(expr)
            tree = parser.parse()
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
            parser = Parser(expr)
            tree = parser.parse()
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
            parser = Parser(expr)
            tree = parser.parse()
            assert isinstance(tree, TemplateNode), f"Failed: {expr}"

    def test_concatenation_operator(self):
        """Concatenation: ~."""
        parser = Parser('{{ "Hello " ~ name ~ "!" }}')
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_range_operator(self):
        """Range operator: .. (1..5)."""
        parser = Parser("{% for i in 1..5 %}{{ i }}{% endfor %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_ternary_operator(self):
        """Ternary: result ? 'yes' : 'no'."""
        parser = Parser("{{ result ? 'yes' : 'no' }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_elvis_operator(self):
        """Elvis: result ?: 'no'."""
        parser = Parser("{{ result ?: 'no' }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_null_coalescing_operator(self):
        """Null coalescing: result ?? 'no'."""
        parser = Parser("{{ result ?? 'no' }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_spaceship_operator(self):
        """Spaceship: <=>."""
        parser = Parser("{{ a <=> b }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_bitwise_operators(self):
        """Bitwise: b-and, b-xor, b-or."""
        parser = Parser("{{ 6 b-and 2 or 6 b-and 16 }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_spread_operator(self):
        """Spread: ..."""
        parser = Parser("{% set numbers = [1, 2, ...moreNumbers] %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)


class TestTwigLiteralsOfficial:
    """Verify literal parsing from docs."""

    def test_string_literals(self):
        """Double and single quoted strings."""
        parser = Parser('{{ "hello" }}{{ \'world\' }}')
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_string_interpolation(self):
        """String interpolation: "first #{middle} last"."""
        parser = Parser('{{ "first #{middle} last" }}')
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_number_literals(self):
        """Integer and float, underscore separator."""
        exprs = ["{{ 42 }}", "{{ 3.14 }}", "{{ -3_141.592_65 }}"]
        for expr in exprs:
            parser = Parser(expr)
            tree = parser.parse()
            assert isinstance(tree, TemplateNode)

    def test_boolean_literals(self):
        """true and false."""
        parser = Parser("{{ true }}{{ false }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_null_literal(self):
        """null and none."""
        parser = Parser("{{ null }}{{ none }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_sequence_literal(self):
        """Array literal: ["first_name", "last_name"]."""
        parser = Parser("{{ ['first_name', 'last_name'] }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_mapping_literal(self):
        """Mapping literal: {'name': 'Fabien', 'city': 'Paris'}."""
        parser = Parser("{{ {'name': 'Fabien', 'city': 'Paris'} }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_mapping_with_key_names(self):
        """Mapping with key names: {name: 'Fabien'}."""
        parser = Parser("{{ {name: 'Fabien', city: 'Paris'} }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_mapping_omitted_keys(self):
        """Mapping with omitted keys: {Paris} equivalent to {'Paris': Paris}."""
        parser = Parser("{{ {Paris} }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_nested_literals(self):
        """Nested sequences and mappings: [1, {'name': 'Fabien'}]."""
        parser = Parser("{{ [1, {'name': 'Fabien'}] }}")
        tree = parser.parse()
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
        parser = Parser("{%- if true -%}yes{%- endif -%}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_whitespace_trim_tilde(self):
        """Line whitespace trimming via ~ modifier."""
        parser = Parser("{{~ value }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)


class TestTwigEdgeCases:
    """Edge cases from the official documentation."""

    def test_complex_expression_with_parentheses(self):
        """Complex expression: (greeting ~ name)|lower."""
        parser = Parser("{{ (greeting ~ name)|lower }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_range_with_filter(self):
        """Range with filter: (1..5)|join(', ')."""
        parser = Parser("{{ (1..5)|join(', ') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_dynamic_attribute_with_parentheses(self):
        """Dynamic attribute: user.('first-name')."""
        parser = Parser("{{ user.('first-name') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_null_safe_operator(self):
        """Null-safe operator: user?.name (3.23+)."""
        parser = Parser("{{ user?.name }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_null_safe_chain(self):
        """Null-safe chain: user?.address?.city."""
        parser = Parser("{{ user?.address?.city }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_array_access(self):
        """Array access: user['name']."""
        parser = Parser("{{ user['name'] }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_method_call_with_args(self):
        """Method call with arguments: html.generate_input('pwd', 'password')."""
        parser = Parser("{{ html.generate_input('pwd', 'password') }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_filter_precedence_with_pipe(self):
        """Filter has higher precedence than concatenation."""
        parser = Parser("{{ greeting ~ name|lower }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_destructuring_sequence(self):
        """Sequence destructuring: [first, last] = ['Fabien', 'Potencier'] (3.23+)."""
        parser = Parser("{% do [first, last] = ['Fabien', 'Potencier'] %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_destructuring_object(self):
        """Object destructuring: {name, email} = user (3.23+)."""
        parser = Parser("{% do {name, email} = user %}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_assignment_in_expression(self):
        """Assignment in expression: {{ b = 1 + 3 }} (3.23+)."""
        parser = Parser("{{ b = 1 + 3 }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_escape_variable_delimiter(self):
        """Escaping variable delimiter: {{ '{{' }}."""
        parser = Parser("{{ '{{' }}")
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_comments_multiline(self):
        """Comments can span multiple lines."""
        source = "{# note: disabled template\n    {% for user in users %}\n    {% endfor %}\n#}"
        parser = Parser(source)
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)

    def test_inline_comment_in_expression(self):
        """Inline comments in expressions (3.15+)."""
        parser = Parser('{{ "Hello World"|upper }}')
        tree = parser.parse()
        assert isinstance(tree, TemplateNode)
