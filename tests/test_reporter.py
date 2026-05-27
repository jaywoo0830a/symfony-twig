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

class TestReporter:
    def test_json_output(self):
        from twig_analyzer.reporter import report_json
        from twig_analyzer.diagnostics import AnalysisResult

        result = AnalysisResult(file_path="test.twig")
        result = result.add(Diagnostic(
            message="Test error",
            severity=Severity.ERROR,
            range=Range(1, 1, 1, 5),
            rule_id="TEST-001",
        ))
        output = report_json([result])
        data = json.loads(output)
        assert "files" in data
        assert "test.twig" in data["files"]
        assert len(data["diagnostics"]) == 1

    def test_console_output(self):
        from twig_analyzer.reporter import report_console
        from twig_analyzer.diagnostics import AnalysisResult

        result = AnalysisResult(file_path="test.twig")
        result = result.add(Diagnostic(
            message="Test error",
            severity=Severity.ERROR,
            range=Range(1, 1, 1, 5),
            rule_id="TEST-001",
        ))
        output = report_console([result])
        assert "Test error" in output
        assert "TEST-001" in output


# ============================================================
# Diagnostics Tests
# ============================================================
