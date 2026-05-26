"""Built-in Twig 3.x definitions: tags, filters, functions, tests, and deprecated features.

Based on https://twig.symfony.com/doc/3.x/ documentation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Built-in Tags
# ---------------------------------------------------------------------------
BUILTIN_TAGS: Dict[str, dict] = {
    "apply": {
        "block": True,
        "description": "Applies a filter to a section of code",
        "since": "1.0",
        "example": "{% apply upper %}Text{% endapply %}",
    },
    "autoescape": {
        "block": True,
        "description": "Controls auto-escaping strategy for a block",
        "since": "1.0",
        "example": "{% autoescape 'html' %}...{% endautoescape %}",
    },
    "block": {
        "block": True,
        "description": "Defines a block that child templates can override",
        "since": "1.0",
        "example": "{% block title %}...{% endblock %}",
    },
    "cache": {
        "block": True,
        "description": "Caches a template fragment",
        "since": "3.2",
        "example": "{% cache %}...{% endcache %}",
    },
    "deprecated": {
        "block": True,
        "description": "Marks a template section as deprecated",
        "since": "1.36",
        "example": "{% deprecated 'Use X instead' %}...{% enddeprecated %}",
    },
    "do": {
        "block": False,
        "description": "Executes an expression without output",
        "since": "1.0",
        "example": "{% do variable = 'value' %}",
    },
    "embed": {
        "block": True,
        "description": "Embeds another template with block overrides",
        "since": "1.8",
        "example": "{% embed 'template.twig' %}...{% endembed %}",
    },
    "extends": {
        "block": False,
        "description": "Extends a parent template (must be the first tag)",
        "since": "1.0",
        "example": "{% extends 'base.html.twig' %}",
    },
    "flush": {
        "block": False,
        "description": "Flushes the output buffer",
        "since": "1.5",
        "example": "{% flush %}",
    },
    "for": {
        "block": True,
        "description": "Iterates over a sequence",
        "since": "1.0",
        "example": "{% for item in items %}...{% endfor %}",
    },
    "from": {
        "block": False,
        "description": "Imports macro names from a template",
        "since": "1.0",
        "example": "{% from 'macros.twig' import input %}",
    },
    "guard": {
        "block": True,
        "description": "Conditionally outputs content based on a tag",
        "since": "3.13",
        "example": "{% guard function('route') %}...{% endguard %}",
    },
    "if": {
        "block": True,
        "description": "Conditional block",
        "since": "1.0",
        "example": "{% if condition %}...{% endif %}",
    },
    "import": {
        "block": False,
        "description": "Imports a template's macros",
        "since": "1.0",
        "example": "{% import 'macros.twig' as macros %}",
    },
    "include": {
        "block": False,
        "description": "Includes another template (tag form)",
        "since": "1.0",
        "example": "{% include 'template.twig' %}",
    },
    "macro": {
        "block": True,
        "description": "Defines a reusable macro",
        "since": "1.0",
        "example": "{% macro input(name, value) %}...{% endmacro %}",
    },
    "sandbox": {
        "block": True,
        "description": "Enables sandbox mode for a block",
        "since": "1.0",
        "example": "{% sandbox %}...{% endsandbox %}",
    },
    "set": {
        "block": True,
        "description": "Assigns values to variables",
        "since": "1.0",
        "example": "{% set name = 'Fabien' %}",
    },
    "types": {
        "block": True,
        "description": "Declares variable types for static analysis",
        "since": "3.15",
        "example": "{% types {name: 'string', age: 'int'} %}",
    },
    "use": {
        "block": False,
        "description": "Imports blocks from another template (horizontal reuse)",
        "since": "1.0",
        "example": "{% use 'blocks.twig' %}",
    },
    "verbatim": {
        "block": True,
        "description": "Outputs raw text without parsing",
        "since": "1.0",
        "example": "{% verbatim %}...{% endverbatim %}",
    },
    "with": {
        "block": True,
        "description": "Creates a new inner scope with variables",
        "since": "1.0",
        "example": "{% with {name: 'Fabien'} %}...{% endwith %}",
    },

    # -- Symfony custom tags --
    "form_theme": {
        "block": False,
        "description": "[Symfony] Sets form theme resources for a form view",
        "since": "—",
        "example": "{% form_theme form \"form/fields.html.twig\" %}",
    },
    "trans": {
        "block": True,
        "description": "[Symfony] Renders translated content block",
        "since": "—",
        "example": "{% trans %}Hello %name%{% endtrans %}",
    },
    "trans_default_domain": {
        "block": False,
        "description": "[Symfony] Sets the default translation domain for a template",
        "since": "—",
        "example": "{% trans_default_domain \"app\" %}",
    },
    "stopwatch": {
        "block": True,
        "description": "[Symfony] Times a template block in the profiler",
        "since": "—",
        "example": "{% stopwatch 'event_name' %}...{% endstopwatch %}",
    },
}

# Tags that require matching end tags
BLOCK_TAGS: Set[str] = {tag for tag, info in BUILTIN_TAGS.items() if info["block"]}

# End tag mapping
END_TAG_MAP: Dict[str, str] = {
    "apply": "endapply",
    "autoescape": "endautoescape",
    "block": "endblock",
    "cache": "endcache",
    "deprecated": "enddeprecated",
    "embed": "endembed",
    "for": "endfor",
    "guard": "endguard",
    "if": "endif",
    "macro": "endmacro",
    "sandbox": "endsandbox",
    "set": "endset",
    "types": "endtypes",
    "verbatim": "endverbatim",
    "with": "endwith",
    "trans": "endtrans",
    "stopwatch": "endstopwatch",
}

# Tags that can have elseif/else between
CONDITIONAL_TAGS: Set[str] = {"if", "for"}

# ---------------------------------------------------------------------------
# Built-in Filters
# ---------------------------------------------------------------------------
BUILTIN_FILTERS: Dict[str, dict] = {
    "abs": {"args": 0, "since": "1.0"},
    "batch": {"args": 2, "since": "1.0"},
    "capitalize": {"args": 0, "since": "1.0"},
    "column": {"args": 1, "since": "2.8"},
    "convert_encoding": {"args": 2, "since": "1.0"},
    "country_name": {"args": 1, "since": "2.12"},
    "currency_name": {"args": 1, "since": "2.12"},
    "currency_symbol": {"args": 1, "since": "2.12"},
    "data_uri": {"args": 1, "since": "1.0"},
    "date": {"args": 2, "since": "1.0"},
    "date_modify": {"args": 1, "since": "1.0"},
    "default": {"args": 1, "since": "1.0"},
    "escape": {"args": 1, "since": "1.0"},
    "e": {"args": 1, "since": "1.0", "alias_of": "escape"},
    "filter": {"args": 1, "since": "2.9"},
    "find": {"args": 1, "since": "3.2"},
    "first": {"args": 0, "since": "1.0"},
    "format": {"args": -1, "since": "1.0"},
    "format_currency": {"args": 2, "since": "2.12"},
    "format_date": {"args": 2, "since": "2.12"},
    "format_datetime": {"args": 2, "since": "2.12"},
    "format_number": {"args": 1, "since": "2.12"},
    "format_time": {"args": 2, "since": "2.12"},
    "html_attr_merge": {"args": 1, "since": "3.18"},
    "html_attr_type": {"args": 1, "since": "3.18"},
    "html_to_markdown": {"args": 0, "since": "2.12"},
    "inline_css": {"args": 0, "since": "3.10"},
    "inky_to_html": {"args": 0, "since": "2.12"},
    "invoke": {"args": -1, "since": "3.19"},
    "join": {"args": 1, "since": "1.0"},
    "json_encode": {"args": 1, "since": "1.0"},
    "keys": {"args": 0, "since": "1.0"},
    "language_name": {"args": 1, "since": "2.12"},
    "last": {"args": 0, "since": "1.0"},
    "length": {"args": 0, "since": "1.0"},
    "locale_name": {"args": 1, "since": "2.12"},
    "lower": {"args": 0, "since": "1.0"},
    "map": {"args": 1, "since": "2.9"},
    "markdown_to_html": {"args": 0, "since": "2.12"},
    "merge": {"args": 1, "since": "1.0"},
    "nl2br": {"args": 0, "since": "1.0"},
    "number_format": {"args": 3, "since": "1.0"},
    "plural": {"args": 2, "since": "3.16"},
    "raw": {"args": 0, "since": "1.0"},
    "reduce": {"args": 2, "since": "2.9"},
    "replace": {"args": 1, "since": "1.0"},
    "reverse": {"args": 0, "since": "1.0"},
    "round": {"args": 2, "since": "1.0"},
    "shuffle": {"args": 0, "since": "3.16"},
    "singular": {"args": 1, "since": "3.16"},
    "slice": {"args": 3, "since": "1.0"},
    "slug": {"args": 1, "since": "1.0"},
    "sort": {"args": 1, "since": "1.0"},
    "spaceless": {"args": 0, "since": "1.0"},
    "split": {"args": 2, "since": "1.0"},
    "striptags": {"args": 0, "since": "1.0"},
    "timezone_name": {"args": 1, "since": "2.12"},
    "title": {"args": 0, "since": "1.0"},
    "trim": {"args": 0, "since": "1.0"},
    "u": {"args": 0, "since": "2.12"},
    "upper": {"args": 0, "since": "1.0"},
    "url_encode": {"args": 0, "since": "1.0"},
}

# ---------------------------------------------------------------------------
# Built-in Functions
# ---------------------------------------------------------------------------
BUILTIN_FUNCTIONS: Dict[str, dict] = {
    "attribute": {"args": -1, "since": "1.0"},
    "block": {"args": 2, "since": "1.0"},
    "constant": {"args": 1, "since": "1.0"},
    "country_names": {"args": 1, "since": "3.12"},
    "country_timezones": {"args": 1, "since": "3.12"},
    "currency_names": {"args": 1, "since": "3.12"},
    "cycle": {"args": 2, "since": "1.0"},
    "date": {"args": 2, "since": "1.0"},
    "dump": {"args": -1, "since": "1.0"},
    "enum": {"args": 1, "since": "3.15"},
    "enum_cases": {"args": 1, "since": "3.17"},
    "html_attr": {"args": 1, "since": "3.18"},
    "html_classes": {"args": -1, "since": "3.17"},
    "html_cva": {"args": 1, "since": "3.17"},
    "include": {"args": -1, "since": "1.0"},
    "language_names": {"args": 1, "since": "3.12"},
    "locale_names": {"args": 1, "since": "3.12"},
    "max": {"args": -1, "since": "1.0"},
    "min": {"args": -1, "since": "1.0"},
    "parent": {"args": 0, "since": "1.0"},
    "random": {"args": 1, "since": "1.0"},
    "range": {"args": 3, "since": "1.0"},
    "script_names": {"args": 1, "since": "3.12"},
    "source": {"args": 1, "since": "1.0"},
    "template_from_string": {"args": -1, "since": "1.0"},
    "timezone_names": {"args": 1, "since": "3.12"},
    # Symfony functions
    "path": {"args": 3, "since": "—"},
    "url": {"args": 3, "since": "—"},
    "asset": {"args": 2, "since": "—"},
    "render": {"args": 2, "since": "—"},
    "render_esi": {"args": 2, "since": "—"},
    "controller": {"args": 3, "since": "—"},
    "is_granted": {"args": 2, "since": "—"},
    "csrf_token": {"args": 1, "since": "—"},
    "absolute_url": {"args": 1, "since": "—"},
    "relative_path": {"args": 1, "since": "—"},
    "asset_version": {"args": 2, "since": "—"},
    "logout_path": {"args": 1, "since": "—"},
    "logout_url": {"args": 1, "since": "—"},
    "impersonation_path": {"args": 1, "since": "—"},
    "impersonation_url": {"args": 1, "since": "—"},
    "impersonation_exit_path": {"args": 1, "since": "—"},
    "impersonation_exit_url": {"args": 1, "since": "—"},
    "is_granted_for_user": {"args": 3, "since": "—"},
    "t": {"args": 3, "since": "—"},
    "expression": {"args": 1, "since": "—"},
    "importmap": {"args": 0, "since": "—"},
    "form": {"args": 2, "since": "—"},
    "form_start": {"args": 2, "since": "—"},
    "form_end": {"args": 2, "since": "—"},
    "form_widget": {"args": 2, "since": "—"},
    "form_label": {"args": 3, "since": "—"},
    "form_help": {"args": 1, "since": "—"},
    "form_errors": {"args": 1, "since": "—"},
    "form_row": {"args": 2, "since": "—"},
    "form_rest": {"args": 2, "since": "—"},
    "form_parent": {"args": 1, "since": "—"},
    "field_name": {"args": 1, "since": "—"},
    "field_value": {"args": 1, "since": "—"},
    "field_label": {"args": 1, "since": "—"},
    "field_help": {"args": 1, "since": "—"},
    "field_errors": {"args": 1, "since": "—"},
    "field_id": {"args": 1, "since": "—"},
    "field_choices": {"args": 1, "since": "—"},
}

# ---------------------------------------------------------------------------
# Built-in Tests
# ---------------------------------------------------------------------------
BUILTIN_TESTS: Dict[str, dict] = {
    "constant": {"args": 1, "since": "1.0"},
    "defined": {"args": 0, "since": "1.0"},
    "divisible by": {"args": 1, "since": "1.0"},
    "divisibleby": {"args": 1, "since": "1.0", "alias_of": "divisible by"},
    "empty": {"args": 0, "since": "1.0"},
    "even": {"args": 0, "since": "1.0"},
    "iterable": {"args": 0, "since": "1.0"},
    "mapping": {"args": 0, "since": "3.14"},
    "null": {"args": 0, "since": "1.0"},
    "odd": {"args": 0, "since": "1.0"},
    "same as": {"args": 1, "since": "1.0"},
    "sameas": {"args": 1, "since": "1.0", "alias_of": "same as"},
    "sequence": {"args": 0, "since": "3.14"},
}

# ---------------------------------------------------------------------------
# Global Variables (always available)
# ---------------------------------------------------------------------------
GLOBAL_VARIABLES: Set[str] = {"_self", "_context", "_charset", "loop"}

# ---------------------------------------------------------------------------
# Deprecated Features (tagged with version)
# ---------------------------------------------------------------------------
DEPRECATED: Dict[str, dict] = {
    # Deprecated in Twig 3.x
    "spaceless": {
        "type": "filter",
        "since": "3.7",
        "message": "Use the 'spaceless' tag instead, or apply 'spaceless' filter via 'apply' tag",
        "removed_in": "4.0",
    },
    "include": {
        "type": "tag",
        "since": "3.12",
        "message": "Use the 'include()' function instead of the '{% include %}' tag",
        "removed_in": "4.0",
    },
    "if/endif": {
        "type": "syntax",
        "since": "3.0",
        "message": "Nested 'if' conditions used with '{% if a and b %}' instead of '{% if a %}{% if b %}'",
        "removed_in": None,
    },
    "flush": {
        "type": "tag",
        "since": "3.4",
        "message": "The 'flush' tag is deprecated and may be removed",
        "removed_in": "4.0",
    },
}

# Precedence levels (higher = binds tighter)
PRECEDENCE = {
    "...": 512,     # Spread
    "|": 300,       # Filter
    "()": 300,      # Function call
    ".": 300,       # Attribute access
    "?.": 300,
    "[]": 300,      # Array access
    "??": 5,        # Null coalescing
    "=>": 250,      # Arrow function
    "**": 200,      # Power
    "is": 100,      # Tests
    "is not": 100,
    "*": 60,
    "/": 60,
    "//": 60,
    "%": 60,
    "not": 70,      # (50 -> 70 in 4.0)
    "~": 27,        # (40 -> 27 in 4.0)
    "+": 30,
    "-": 30,
    "..": 25,
    "==": 20, "!=": 20, "<=>": 20, "<": 20, ">": 20, ">=": 20, "<=": 20,
    "not in": 20, "in": 20, "matches": 20,
    "starts with": 20, "ends with": 20,
    "has some": 20, "has every": 20,
    "===": 20, "!==": 20,
    "b-and": 18, "b-xor": 17, "b-or": 16,
    "and": 15, "xor": 12, "or": 10,
    "?:": 5, "? :": 5,
    "=": 0,         # Assignment
}

# Escape strategies
ESCAPE_STRATEGIES: Set[str] = {"html", "js", "css", "url", "html_attr", "html_attr_relaxed", "name"}

# Safe filter list (filters that mark output as safe)
SAFE_FILTERS: Set[str] = {"raw", "escape", "e"}
