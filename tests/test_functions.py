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
