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
