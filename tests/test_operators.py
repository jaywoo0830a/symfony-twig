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
