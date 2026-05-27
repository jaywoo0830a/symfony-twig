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
