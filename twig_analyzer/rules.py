"""Analysis rules for Twig static analyzer — pure functions.

Each rule: (TemplateNode, str) → Tuple[Diagnostic, ...]
"""

from __future__ import annotations
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
# 1. AST walker (pure: (Node, Callable) → None, but collects via side-list)
# ═══════════════════════════════════════════════════════════════════════

def walk(node: Node, visitor: Callable[[Node], None]) -> None:
    """Walk AST depth-first, calling visitor on each node."""
    visitor(node)

    if isinstance(node, TemplateNode):
        for c in node.body:
            walk(c, visitor)
    elif isinstance(node, BlockTagNode):
        for c in node.body:
            walk(c, visitor)
        for c in node.else_body:
            walk(c, visitor)
        for clause in node.elseif_clauses:
            for c in clause.get("body", ()):
                walk(c, visitor)
    elif isinstance(node, PrintNode) and node.expression:
        walk(node.expression, visitor)
    elif isinstance(node, FilterNode):
        if node.target:
            walk(node.target, visitor)
        for a in node.args:
            walk(a, visitor)
    elif isinstance(node, FunctionCallNode):
        for a in node.args:
            walk(a, visitor)
    elif isinstance(node, TestNode):
        if node.target:
            walk(node.target, visitor)
        for a in node.args:
            walk(a, visitor)
    elif isinstance(node, BinaryOpNode):
        if node.left:
            walk(node.left, visitor)
        if node.right:
            walk(node.right, visitor)
    elif isinstance(node, UnaryOpNode) and node.operand:
        walk(node.operand, visitor)
    elif isinstance(node, ArrayNode):
        for item in node.items:
            walk(item, visitor)
    elif isinstance(node, MappingNode):
        for v in node.items.values():
            walk(v, visitor)
    elif isinstance(node, NamedArgNode) and node.value:
        walk(node.value, visitor)


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
                diags.append(Diagnostic(
                    message="'extends' must be the first tag in the template.",
                    severity=Severity.ERROR,
                    range=Range(child.line, child.column, child.line, child.column + 7),
                    rule_id="TWIG-EXTENDS-FIRST",
                ))
            found_non_empty = True
        else:
            found_non_empty = True
    return tuple(diags)


def check_undefined_filters(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, FilterNode) and node.name and node.name not in BUILTIN_FILTERS:
            diags.append(Diagnostic(
                message=f"Unknown filter '{node.name}'.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-UNKNOWN-FILTER",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_undefined_functions(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, FunctionCallNode) and node.name and node.name not in BUILTIN_FUNCTIONS:
            diags.append(Diagnostic(
                message=f"Unknown function '{node.name}()'.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-UNKNOWN-FUNCTION",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_undefined_tests(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, TestNode) and node.name and node.name not in BUILTIN_TESTS:
            diags.append(Diagnostic(
                message=f"Unknown test '{node.name}'.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-UNKNOWN-TEST",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_deprecated_features(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, (BlockTagNode, InlineTagNode)):
            if node.name in DEPRECATED and DEPRECATED[node.name]["type"] == "tag":
                info = DEPRECATED[node.name]
                diags.append(Diagnostic(
                    message=f"Deprecated tag '{node.name}': {info['message']}",
                    severity=Severity.WARNING,
                    range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                    rule_id="TWIG-DEPRECATED-TAG",
                ))
        if isinstance(node, FilterNode) and node.name in DEPRECATED and DEPRECATED[node.name]["type"] == "filter":
            info = DEPRECATED[node.name]
            diags.append(Diagnostic(
                message=f"Deprecated filter '{node.name}': {info['message']}",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-DEPRECATED-FILTER",
            ))
    walk(tree, visit)
    return tuple(diags)


def check_raw_filter_usage(tree: TemplateNode, source: str) -> Tuple[Diagnostic, ...]:
    diags: list[Diagnostic] = []
    def visit(node: Node):
        if isinstance(node, FilterNode) and node.name == "raw":
            diags.append(Diagnostic(
                message="Using 'raw' filter disables auto-escaping. Ensure content is trusted.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + 3),
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
    diags: list[Diagnostic] = []
    defined: set[str] = set(GLOBAL_VARIABLES)
    used_before_defined: list[tuple[str, int, int]] = []

    def collect_sets(node: Node):
        if isinstance(node, InlineTagNode) and node.name == "set":
            # Extract set variable names (works for both single and multiple assignment)
            for arg in node.args:
                if isinstance(arg, LiteralNode) and isinstance(arg.value, str):
                    defined.add(arg.value)
                elif isinstance(arg, VariableNode):
                    defined.add(arg.name)

    def check_uses(node: Node):
        if isinstance(node, VariableNode):
            if node.name not in defined and not node.attributes:
                used_before_defined.append((node.name, node.line, node.column))
        elif isinstance(node, PrintNode) and node.expression:
            pass  # Expression walk handles this

    walk(tree, collect_sets)

    def check_var(node: Node):
        if isinstance(node, VariableNode):
            parts = [node.name] + list(node.attributes)
            if parts[0] not in defined and parts[0] not in ('loop',):
                diags.append(Diagnostic(
                    message=f"Variable '{parts[0]}' may not be defined.",
                    severity=Severity.WARNING,
                    range=Range(node.line, node.column, node.line, node.column + len(parts[0])),
                    rule_id="TWIG-UNDEFINED-VAR",
                ))

    walk(tree, check_var)
    return tuple(diags)


# ═══════════════════════════════════════════════════════════════════════
# 3. Registry
# ═══════════════════════════════════════════════════════════════════════

ALL_RULES: Dict[str, RuleFunc] = {
    "extends-first": check_extends_first,
    "undefined-filters": check_undefined_filters,
    "undefined-functions": check_undefined_functions,
    "undefined-tests": check_undefined_tests,
    "deprecated-features": check_deprecated_features,
    "raw-filter": check_raw_filter_usage,
    "missing-escape": check_missing_escape,
    "hardcoded-text": check_hardcoded_strings,
    "variable-usage": check_variable_usage,
}

DEFAULT_SEVERITIES: Dict[str, Severity] = {
    "extends-first": Severity.ERROR,
    "undefined-filters": Severity.WARNING,
    "undefined-functions": Severity.WARNING,
    "undefined-tests": Severity.WARNING,
    "deprecated-features": Severity.WARNING,
    "raw-filter": Severity.WARNING,
    "missing-escape": Severity.HINT,
    "hardcoded-text": Severity.HINT,
    "variable-usage": Severity.WARNING,
}
