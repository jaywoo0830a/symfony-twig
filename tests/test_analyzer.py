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
