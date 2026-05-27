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

class TestTwigFiltersOfficial:
    """Verify built-in filters from https://twig.symfony.com/doc/3.x/"""

    def test_all_filters_recognized(self):
        """All built-in filters should not trigger unknown-filter warning."""
        analyzer = Analyzer()
        for filter_name in BUILTIN_FILTERS:
            if filter_name == "spaceless":
                continue  # Deprecated, tested separately
            source = f"{{{{ 'test'|{filter_name} }}}}"
            result = analyzer.analyze(source)
            unknowns = [d for d in result.diagnostics if d.rule_id == "TWIG-UNKNOWN-FILTER"]
            assert len(unknowns) == 0, f"Filter '{filter_name}' reported as unknown"

    def test_filter_chaining(self):
        """Multiple filters can be chained: name|striptags|title."""
        tree = parse("{{ name|striptags|title }}")
        assert isinstance(tree, TemplateNode)

    def test_filter_with_arguments(self):
        """Filters can accept arguments: list|join(', ')."""
        tree = parse("{{ list|join(', ') }}")
        assert isinstance(tree, TemplateNode)

    def test_filter_named_arguments(self):
        """Filters support named arguments: data|convert_encoding(from: 'iso-2022-jp', to: 'UTF-8')."""
        tree = parse("{{ data|convert_encoding(from: 'iso-2022-jp', to: 'UTF-8') }}")
        assert isinstance(tree, TemplateNode)

    def test_escape_filter_strategies(self):
        """Escape filter with strategies: e('js'), e('css'), e('url'), e('html_attr')."""
        for strategy in ['js', 'css', 'url', 'html_attr']:
            tree = parse(f"{{{{ user.username|e('{strategy}') }}}}")
            assert isinstance(tree, TemplateNode)

    def test_default_filter(self):
        """Default filter: {{ var|default('fallback') }}."""
        tree = parse("{{ var|default('fallback') }}")
        assert isinstance(tree, TemplateNode)

    def test_date_filter(self):
        """Date filter: {{ post.publishedAt|date('Y-m-d') }}."""
        tree = parse("{{ post.publishedAt|date('Y-m-d') }}")
        assert isinstance(tree, TemplateNode)

    def test_format_filter(self):
        """Format filter: {{ 'Hello %s!'|format(name) }}."""
        tree = parse("{{ 'Hello %s!'|format(name) }}")
        assert isinstance(tree, TemplateNode)

    def test_merge_filter(self):
        """Merge filter."""
        tree = parse("{{ arr|merge([3, 4]) }}")
        assert isinstance(tree, TemplateNode)

    def test_sort_filter(self):
        """Sort filter."""
        tree = parse("{{ items|sort }}")
        assert isinstance(tree, TemplateNode)

    def test_slice_filter(self):
        """Slice filter: users|slice(0, 10)."""
        tree = parse("{{ users|slice(0, 10) }}")
        assert isinstance(tree, TemplateNode)

    def test_json_encode_filter(self):
        """json_encode filter."""
        tree = parse("{{ data|json_encode }}")
        assert isinstance(tree, TemplateNode)

    def test_upper_lower_title_filters(self):
        """Case-changing filters."""
        for f in ['upper', 'lower', 'title', 'capitalize']:
            tree = parse(f"{{{{ 'hello'|{f} }}}}")
            assert isinstance(tree, TemplateNode), f"Failed for filter {f}"
