"""Analyzer & Rules Tests."""

from twig_analyzer.analyzer import Analyzer
from twig_analyzer.diagnostics import Severity


class TestAnalyzer:
    def test_no_issues_clean_template(self):
        analyzer = Analyzer()
        result = analyzer.analyze("Hello {{ name|upper }}")
        assert len(result.errors) == 0

    def test_unknown_filter(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{{ name|nonexistent_filter_xyz }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-UNKNOWN-FILTER"]
        assert len(warnings) >= 1

    def test_unknown_function(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{{ nonexistent_func_xyz() }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-UNKNOWN-FUNCTION"]
        assert len(warnings) >= 1

    def test_extends_not_first(self):
        analyzer = Analyzer()
        result = analyzer.analyze("Hello\n{% extends 'base.html.twig' %}")
        errors = [d for d in result.diagnostics if d.rule_id == "TWIG-EXTENDS-FIRST"]
        assert len(errors) >= 1

    def test_raw_filter_warning(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{{ html|raw }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-RAW-FILTER"]
        assert len(warnings) >= 1

    def test_disabled_rule(self):
        analyzer = Analyzer(rules={"raw-filter": False})
        result = analyzer.analyze("{{ html|raw }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-RAW-FILTER"]
        assert len(warnings) == 0

    def test_severity_override(self):
        analyzer = Analyzer(severities={"raw-filter": "error"})
        result = analyzer.analyze("{{ html|raw }}")
        raw_diags = [d for d in result.diagnostics if d.rule_id == "TWIG-RAW-FILTER"]
        assert len(raw_diags) >= 1
        assert raw_diags[0].severity == Severity.ERROR

    def test_deprecated_spaceless(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{{ html|spaceless }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-DEPRECATED-FILTER"]
        assert len(warnings) >= 1

    def test_undefined_variable(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{{ undefined_var_name_xyz }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-UNDEFINED-VAR"]
        assert len(warnings) >= 1

    def test_defined_variable_no_warning(self):
        analyzer = Analyzer()
        result = analyzer.analyze("{% set name = 'Fabien' %}{{ name }}")
        warnings = [d for d in result.diagnostics if d.rule_id == "TWIG-UNDEFINED-VAR" and "name" in d.message]
        assert len(warnings) == 0
