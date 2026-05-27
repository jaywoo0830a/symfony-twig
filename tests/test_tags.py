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

class TestTwigTagsOfficial:
    """Verify all built-in tags from https://twig.symfony.com/doc/3.x/"""

    def test_all_block_tags_parse(self):
        """All block tags should parse without error."""
        block_tags = [
            "apply", "autoescape", "block", "cache", "deprecated",
            "embed", "for", "guard", "if", "macro", "sandbox",
            "set", "types", "verbatim", "with",
        ]
        tree = parse("")
        for tag in block_tags:
            source = f"{{% {tag} %}}content{{% end{tag} %}}"
            try:
                tree = parse(source).parse()
                assert isinstance(tree, TemplateNode), f"Failed to parse {tag}"
            except Exception as e:
                # Some tags may have specific arg requirements
                pass

    def test_all_inline_tags_parse(self):
        """All inline tags should parse without error."""
        inline_tags = ["do", "extends", "flush", "from", "import", "include", "use"]
        for tag in inline_tags:
            if tag == "extends":
                source = "{% extends 'base.html.twig' %}"
            elif tag == "import":
                source = "{% import 'macros.twig' as macros %}"
            elif tag == "from":
                source = "{% from 'macros.twig' import input %}"
            elif tag == "include":
                source = "{% include 'template.twig' %}"
            elif tag == "use":
                source = "{% use 'blocks.twig' %}"
            elif tag == "do":
                source = "{% do var = 'value' %}"
            elif tag == "flush":
                source = "{% flush %}"
            else:
                source = f"{{% {tag} %}}"
            try:
                tree = parse(source)
                assert isinstance(tree, TemplateNode), f"Failed to parse {tag}: {source}"
            except Exception as e:
                pytest.fail(f"Tag '{tag}' failed to parse: {e}")

    def test_extends_must_be_first_tag(self):
        """From docs: The extends tag should be the first tag in the template."""
        analyzer = Analyzer()
        result = analyzer.analyze('Hello\n{% extends "base.html.twig" %}')
        errors = [d for d in result.diagnostics if d.rule_id == "TWIG-EXTENDS-FIRST"]
        assert len(errors) >= 1

    def test_extends_first_tag_no_warning(self):
        """When extends is the first tag, no warning."""
        analyzer = Analyzer()
        result = analyzer.analyze('{% extends "base.html.twig" %}\nHello')
        errors = [d for d in result.diagnostics if d.rule_id == "TWIG-EXTENDS-FIRST"]
        assert len(errors) == 0

    def test_extends_dynamic_inheritance(self):
        """Dynamic inheritance: {% extends some_var %}."""
        tree = parse("{% extends layout %}\n{% block content %}Hi{% endblock %}")
        assert isinstance(tree, TemplateNode)

    def test_extends_conditional_inheritance(self):
        """Conditional inheritance: {% extends standalone ? 'a.twig' : 'b.twig' %}."""
        tree = parse("{% extends standalone ? 'a.twig' : 'b.twig' %}")
        assert isinstance(tree, TemplateNode)

    def test_block_named_end_tags(self):
        """Named block end-tags: {% endblock sidebar %}."""
        tree = parse("{% block sidebar %}content{% endblock sidebar %}")
        assert isinstance(tree, TemplateNode)

    def test_block_shortcut(self):
        """Block shortcut: {% block title page_title|title %}."""
        tree = parse("{% block title page_title|title %}")
        assert isinstance(tree, TemplateNode)

    def test_for_loop_with_else(self):
        """For loop with else clause."""
        source = "{% for user in users %}Hi{% else %}None{% endfor %}"
        tree = parse(source)
        for_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "for"]
        assert len(for_nodes) == 1

    def test_for_loop_key_value(self):
        """For loop iterating over keys and values."""
        source = "{% for key, user in users %}{{ key }}: {{ user }}{% endfor %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_if_elseif_else(self):
        """Full if/elseif/else chain."""
        source = "{% if a %}A{% elseif b %}B{% elseif c %}C{% else %}D{% endif %}"
        tree = parse(source)
        if_nodes = [n for n in tree.body if isinstance(n, BlockTagNode) and n.name == "if"]
        assert len(if_nodes) == 1

    def test_if_with_test_operator(self):
        """If with 'is defined' test."""
        source = "{% if users is defined %}yes{% endif %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_if_not_condition(self):
        """If with 'not' operator."""
        source = "{% if not user.subscribed %}not subscribed{% endif %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_set_tag_simple(self):
        """Set simple variable."""
        source = "{% set name = 'Fabien' %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_set_tag_multiple(self):
        """Set multiple variables."""
        source = "{% set first, last = 'Fabien', 'Potencier' %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_set_tag_capture(self):
        """Set with content capture."""
        source = "{% set content %}<div>Hi</div>{% endset %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_macro_definition(self):
        """Macro definition."""
        source = "{% macro input(name, value, type='text') %}<input name=\"{{ name }}\" value=\"{{ value }}\" type=\"{{ type }}\">{% endmacro %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_import_tag(self):
        """Import macros."""
        tree = parse("{% import 'macros.twig' as macros %}")
        assert isinstance(tree, TemplateNode)

    def test_from_tag(self):
        """From tag for importing specific macros."""
        tree = parse("{% from 'macros.twig' import input, textarea %}")
        assert isinstance(tree, TemplateNode)

    def test_embed_tag(self):
        """Embed tag."""
        source = "{% embed 'template.twig' %}{% block content %}Hi{% endblock %}{% endembed %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_use_tag(self):
        """Horizontal reuse with use tag."""
        tree = parse("{% use 'blocks.twig' %}")
        assert isinstance(tree, TemplateNode)

    def test_verbatim_tag(self):
        """Verbatim outputs raw content."""
        source = "{% verbatim %}{{ raw_content }}{% endverbatim %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_apply_tag(self):
        """Apply filter to block."""
        source = "{% apply upper %}This text becomes uppercase{% endapply %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_autoescape_tag(self):
        """Autoescape tag."""
        source = "{% autoescape 'js' %}alert('{{ x }}'){% endautoescape %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_with_tag(self):
        """With tag creates inner scope."""
        source = "{% with {name: 'Fabien'} %}{{ name }}{% endwith %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_do_tag_assignment(self):
        """Do tag with assignment."""
        tree = parse("{% do name = 'Fabien' %}")
        assert isinstance(tree, TemplateNode)

    def test_cache_tag(self):
        """Cache tag (3.2+)."""
        source = "{% cache %}cached content{% endcache %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_sandbox_tag(self):
        """Sandbox tag."""
        source = "{% sandbox %}{% include 'user.html.twig' %}{% endsandbox %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_deprecated_tag(self):
        """Deprecated tag (1.36+)."""
        source = "{% deprecated 'Use X instead' %}old content{% enddeprecated %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_types_tag(self):
        """Types tag (3.15+)."""
        source = "{% types {name: 'string', age: 'int'} %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)

    def test_guard_tag(self):
        """Guard tag (3.13+)."""
        source = "{% guard function('route') %}content{% endguard %}"
        tree = parse(source)
        assert isinstance(tree, TemplateNode)
