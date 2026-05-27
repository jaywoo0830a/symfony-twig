"""Analysis rules for Twig static analyzer — pure functions.

Each rule: (TemplateNode, str) → Tuple[Diagnostic, ...]

Design:
  - Pure: no mutable state except the diagnostic accumulator list
  - Rule functions are composed with helper pure functions
  - AST walk uses match/case for exhaustive dispatch (Python 3.10+)
  - Collections use tuple/frozenset for immutability
"""

from __future__ import annotations
import re
from functools import reduce
from itertools import chain
from typing import Callable, Dict, FrozenSet, Tuple, Sequence

from .ast import (
    Node, TemplateNode, TextNode, PrintNode,
    BlockTagNode, InlineTagNode, CommentNode,
    VariableNode, LiteralNode, FunctionCallNode, FilterNode, TestNode,
    BinaryOpNode, UnaryOpNode, ArrayNode, MappingNode, NamedArgNode,
)
from .diagnostics import Diagnostic, Range, Severity
from .builtins import (
    BUILTIN_TAGS, BUILTIN_FILTERS, BUILTIN_FUNCTIONS, BUILTIN_TESTS,
    BLOCK_TAGS, END_TAG_MAP, GLOBAL_VARIABLES, DEPRECATED,
)

RuleFunc = Callable[[TemplateNode, str], Tuple[Diagnostic, ...]]


# ═══════════════════════════════════════════════════════════════════════
# 0. Annotation helpers — extract declarations from {# @kind name #} comments
# ═══════════════════════════════════════════════════════════════════════

def _collect_annotations(source: str, kind: str) -> FrozenSet[str]:
    """Extract names from {# @kind name Type? #} annotations.

    Supports:
      {# @filter my_filter #}   {# @function my_func #}
      {# @test my_test #}       {# @tag my_tag #}
      {# @var my_var Type #}    {# @param my_param Type #}
    """
    return frozenset(
        m.group(1)
        for m in re.finditer(r'\{\#\s*@' + kind + r'\s+(\w+)', source)
    )


# ═══════════════════════════════════════════════════════════════════════
# 1. AST walker — match/case dispatch, pure visitor pattern
# ═══════════════════════════════════════════════════════════════════════

_WALK_CHILDREN: Dict[type, Tuple[str, ...]] = {
    TemplateNode:    ("body",),
    BlockTagNode:    ("body", "else_body"),
    PrintNode:       ("expression",),
    FilterNode:      ("target", "args"),
    FunctionCallNode: ("args",),
    TestNode:        ("target", "args"),
    BinaryOpNode:    ("left", "right"),
    UnaryOpNode:     ("operand",),
    ArrayNode:       ("items",),
    MappingNode:     ("items",),  # .values()
    NamedArgNode:    ("value",),
}

def walk(node: Node, visitor: Callable[[Node], None]) -> None:
    """Walk AST depth-first, calling visitor(node) then recursing children.

    Uses match/case for exhaustive type dispatch (Python 3.10+).
    """
    visitor(node)

    match node:
        case TemplateNode(body=body):
            for child in body: walk(child, visitor)
        case BlockTagNode(body=body, else_body=eb, elseif_clauses=ec):
            for child in chain(body, eb):
                walk(child, visitor)
            for clause in ec:
                for child in clause.get("body", ()):
                    walk(child, visitor)
        case PrintNode(expression=expr) if expr is not None:
            walk(expr, visitor)
        case FilterNode(target=tgt, args=args):
            if tgt: walk(tgt, visitor)
            for a in args: walk(a, visitor)
        case FunctionCallNode(args=args):
            for a in args: walk(a, visitor)
        case TestNode(target=tgt, args=args):
            if tgt: walk(tgt, visitor)
            for a in args: walk(a, visitor)
        case BinaryOpNode(left=l, right=r):
            if l: walk(l, visitor)
            if r: walk(r, visitor)
        case UnaryOpNode(operand=op) if op is not None:
            walk(op, visitor)
        case ArrayNode(items=items):
            for item in items: walk(item, visitor)
        case MappingNode(items=items):
            for v in items.values(): walk(v, visitor)
        case NamedArgNode(value=v) if v is not None:
            walk(v, visitor)
        case _:
            pass  # TextNode, CommentNode, LiteralNode, VariableNode — leaf nodes


# ═══════════════════════════════════════════════════════════════════════
# 2. Rules
# ═══════════════════════════════════════════════════════════════════════

def check_extends_first(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    """{% extends %} must be the first tag."""
    diags: list[Diagnostic] = []
    found_non_empty = False
    for child in tree.body:
        if isinstance(child, TextNode) and child.value.strip() == "":
            continue
        if isinstance(child, CommentNode):
            continue
        if isinstance(child, InlineTagNode) and child.name == "extends":
            if found_non_empty:
                start_col = child.column + 1  # skip space after {%
                diags.append(Diagnostic(
                    message="'extends' must be the first tag in the template.",
                    severity=Severity.ERROR,
                    range=Range(child.line, start_col, child.line, start_col + 7),
                    rule_id="TWIG-EXTENDS-FIRST",
                ))
            found_non_empty = True
        else:
            found_non_empty = True
    return tuple(diags)


def check_extends_content_outside_blocks(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    """When using {% extends %}, all content must be inside {% block %} tags."""
    diags: list[Diagnostic] = []
    has_extends = any(
        isinstance(child, InlineTagNode) and child.name == "extends"
        for child in tree.body
    )
    if not has_extends:
        return ()

    for child in tree.body:
        if isinstance(child, TextNode) and child.value.strip():
            diags.append(Diagnostic(
                message="Content outside blocks is ignored when extending a parent template.",
                severity=Severity.WARNING,
                range=Range(child.line, child.column, child.line, child.column + len(child.value)),
                rule_id="TWIG-EXTENDS-CONTENT-OUTSIDE-BLOCK",
            ))
        elif isinstance(child, PrintNode):
            diags.append(Diagnostic(
                message="Expressions outside blocks are ignored when using {% extends %}.",
                severity=Severity.WARNING,
                range=Range(child.line, child.column, child.line, child.column),
                rule_id="TWIG-EXTENDS-CONTENT-OUTSIDE-BLOCK",
            ))
        elif isinstance(child, InlineTagNode) and child.name not in ("extends", "use", "import", "from", "set"):
            diags.append(Diagnostic(
                message=f"Tag '{{% {child.name} %}}' outside blocks is ignored when extending.",
                severity=Severity.WARNING,
                range=Range(child.line, child.column, child.line, child.column + len(child.name)),
                rule_id="TWIG-EXTENDS-CONTENT-OUTSIDE-BLOCK",
            ))
    return tuple(diags)


def check_undefined_filters(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    """Check for unknown filters. Custom filters declared via {# @filter name #} are allowed."""
    known = frozenset(BUILTIN_FILTERS.keys()) | _collect_annotations(source, 'filter')
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, FilterNode) and node.name and node.name not in known:
            # FilterNode.column points to '|', so +1 skips to the filter name
            start_col = node.column + 1
            diags.append(Diagnostic(
                message=f"Unknown filter '{node.name}'. "
                        f"Declare it with {{# @filter {node.name} #}} if it's a custom filter.",
                severity=Severity.WARNING,
                range=Range(node.line, start_col, node.line, start_col + len(node.name)),
                rule_id="TWIG-UNKNOWN-FILTER",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_undefined_functions(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    """Check for unknown functions. Custom functions declared via {# @function name #} are allowed."""
    known = frozenset(BUILTIN_FUNCTIONS.keys()) | _collect_annotations(source, 'function')
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, FunctionCallNode) and node.name and node.name not in known:
            diags.append(Diagnostic(
                message=f"Unknown function '{node.name}()'. "
                        f"Declare it with {{# @function {node.name} #}} if it's a custom function.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-UNKNOWN-FUNCTION",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_undefined_tests(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    """Check for unknown tests. Custom tests declared via {# @test name #} are allowed."""
    known = frozenset(BUILTIN_TESTS.keys()) | _collect_annotations(source, 'test')
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, TestNode) and node.name and node.name not in known:
            diags.append(Diagnostic(
                message=f"Unknown test '{node.name}'. "
                        f"Declare it with {{# @test {node.name} #}} if it's a custom test.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-UNKNOWN-TEST",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_undefined_tags(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    """Check for unknown tags. Custom tags declared via {# @tag name #} are allowed."""
    known = frozenset(BUILTIN_TAGS.keys()) | _collect_annotations(source, 'tag')
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, (BlockTagNode, InlineTagNode)) and node.name and node.name not in known:
            # Skip end tags (endif, endblock etc.) — they derive from known tags
            if node.name.startswith('end'):
                base = node.name[3:]  # remove 'end' prefix
                if base in known:
                    return
            diags.append(Diagnostic(
                message=f"Unknown tag '{{% {node.name} %}}'. "
                        f"Declare it with {{# @tag {node.name} #}} if it's a custom tag.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-UNKNOWN-TAG",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_deprecated_features(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, (BlockTagNode, InlineTagNode)):
            if node.name in DEPRECATED and DEPRECATED[node.name]["type"] == "tag":
                info = DEPRECATED[node.name]
                start_col = node.column + 1  # skip space after {%
                diags.append(Diagnostic(
                    message=f"Deprecated tag '{node.name}': {info['message']}",
                    severity=Severity.WARNING,
                    range=Range(node.line, start_col, node.line, start_col + len(node.name)),
                    rule_id="TWIG-DEPRECATED-TAG",
                ))
        if isinstance(node, FilterNode) and node.name in DEPRECATED and DEPRECATED[node.name]["type"] == "filter":
            info = DEPRECATED[node.name]
            start_col = node.column + 1  # skip '|'
            diags.append(Diagnostic(
                message=f"Deprecated filter '{node.name}': {info['message']}",
                severity=Severity.WARNING,
                range=Range(node.line, start_col, node.line, start_col + len(node.name)),
                rule_id="TWIG-DEPRECATED-FILTER",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_raw_filter_usage(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, FilterNode) and node.name == "raw":
            start_col = node.column + 1  # skip '|'
            diags.append(Diagnostic(
                message="Using 'raw' filter disables auto-escaping. Ensure content is trusted.",
                severity=Severity.WARNING,
                range=Range(node.line, start_col, node.line, start_col + 3),
                rule_id="TWIG-RAW-FILTER",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_missing_escape(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    return ()


def check_hardcoded_strings(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, TextNode) and len(node.value.strip()) > 120:
            diags.append(Diagnostic(
                message="Long hardcoded text string. Consider using translation.",
                severity=Severity.HINT,
                range=Range(node.line, node.column, node.line, node.column + len(node.value)),
                rule_id="TWIG-HARDCODED-TEXT",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_variable_usage(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    """Check for variables that may not be defined.

    Variables are considered defined when declared via:
      1. {% set name = value %}            — explicit assignment
      2. {% for item in items %}           — loop variable
      3. {% types {name: 'type', ...} %}   — Twig 3.15+ type declaration
      4. {# @var name Type #}              — PHP-Doc-style annotation
      5. {# @param name Type #}             — PHPDoc param annotation
      6. Built-in globals (_self, _context, _charset, loop)
      7. Symfony globals (app, form)
    """
    diags: list[Diagnostic] = []
    defined: set[str] = set(GLOBAL_VARIABLES)
    defined.update({'app', 'form'})  # Symfony global variables

    # ── 1. {% types {varName: 'type', ...} %} — Twig 3.15+ official syntax ──
    for m in re.finditer(r'\{%-?\s*types\s+\{([^}]+)\}\s*-?%\}', source):
        mapping_str = m.group(1)
        for vm in re.finditer(r'(\w+)\s*:', mapping_str):
            defined.add(vm.group(1))

    # ── 2. {# @var name Type #} / {# @param name Type #} — PHPDoc style ──
    for m in re.finditer(r'\{\#\s*@(?:var|param)\s+(\w+)', source):
        defined.add(m.group(1))

    # ── 3. {% for item in items %} / {% for key, item in items %} — loop vars ──
    for m in re.finditer(r'\{%-?\s*for\s+(\w+(?:\s*,\s*\w+)*)\s+in\b', source):
        vars_str = m.group(1)
        for v in re.finditer(r'(\w+)', vars_str):
            defined.add(v.group(1))

    # ── 4. {% set name = value %} — explicit assignment ──
    for m in re.finditer(r'\{%-?\s*set\s+(\w+)\s*=', source):
        defined.add(m.group(1))

    # ── 5. Collect definitions from AST (InlineTagNode set tags) ──
    def collect_definitions(node: Node):
        """Collect variable names from inline set tags (args already parsed)."""
        if isinstance(node, InlineTagNode) and node.name == "set":
            for arg in node.args:
                if isinstance(arg, LiteralNode) and isinstance(arg.value, str):
                    defined.add(arg.value)
                elif isinstance(arg, VariableNode):
                    defined.add(arg.name)

    walk(tree, collect_definitions)

    # ── 4. Check variable usage ──
    def check_var(node: Node):
        if isinstance(node, VariableNode):
            parts = [node.name] + list(node.attributes)
            name = parts[0]
            # Skip if defined, loop variable, or looks like a common external variable
            if name in defined or name == 'loop':
                return
            # Skip variables starting with _ (private/internal convention)
            if name.startswith('_'):
                return

            diags.append(Diagnostic(
                message=f"Variable '{name}' may not be defined. "
                        f"Use {{% types {{{name}: 'type'}} %}} or {{# @var {name} Type #}} to declare it.",
                severity=Severity.HINT,  # HINT instead of WARNING — less intrusive
                range=Range(node.line, node.column, node.line, node.column + len(name)),
                rule_id="TWIG-UNDEFINED-VAR",
            ))

    walk(tree, check_var)
    return tuple(diags)


# ═══════════════════════════════════════════════════════════════════════
# 3. Registry
# ═══════════════════════════════════════════════════════════════════════

ALL_RULES: Dict[str, RuleFunc] = {
    "extends-first": check_extends_first,
    "extends-content-outside-block": check_extends_content_outside_blocks,
    "undefined-filters": check_undefined_filters,
    "undefined-functions": check_undefined_functions,
    "undefined-tests": check_undefined_tests,
    "undefined-tags": check_undefined_tags,
    "deprecated-features": check_deprecated_features,
    "raw-filter": check_raw_filter_usage,
    "missing-escape": check_missing_escape,
    "hardcoded-text": check_hardcoded_strings,
    "variable-usage": check_variable_usage,
}

DEFAULT_SEVERITIES: Dict[str, Severity] = {
    "extends-first": Severity.ERROR,
    "extends-content-outside-block": Severity.WARNING,
    "undefined-filters": Severity.WARNING,
    "undefined-functions": Severity.WARNING,
    "undefined-tests": Severity.WARNING,
    "undefined-tags": Severity.WARNING,
    "deprecated-features": Severity.WARNING,
    "raw-filter": Severity.WARNING,
    "missing-escape": Severity.HINT,
    "hardcoded-text": Severity.HINT,
    "variable-usage": Severity.HINT,   # HINT: controller vars are external
}
