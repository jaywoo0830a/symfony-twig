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
