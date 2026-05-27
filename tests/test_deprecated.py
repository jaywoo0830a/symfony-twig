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
