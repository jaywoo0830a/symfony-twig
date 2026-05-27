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

class TestDiagnostics:
    def test_lsp_format(self):
        diag = Diagnostic(
            message="Test",
            severity=Severity.WARNING,
            range=Range(2, 3, 2, 8),
            rule_id="R001",
        )
        d = diag.to_lsp()
        assert d["severity"] == 2  # Warning
        assert d["range"]["start"]["line"] == 1  # 0-indexed
        assert d["range"]["start"]["character"] == 2
        assert d["code"] == "R001"
        assert d["source"] == "twig-analyzer"


# ============================================================
# Official Twig 3.x Documentation – Comprehensive Tests
# ============================================================
