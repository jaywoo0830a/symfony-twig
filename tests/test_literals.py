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
