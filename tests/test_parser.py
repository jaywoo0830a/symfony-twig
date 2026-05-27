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
