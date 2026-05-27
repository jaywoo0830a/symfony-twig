"""Unit tests for Twig Static Analyzer."""

import json
import tempfile
import os
import pytest

# Add parent directory to path

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
