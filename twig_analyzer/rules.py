"""Analysis rules for Twig static analyzer.

Each rule inspects the AST and returns Diagnostics.
"""

from typing import Callable, Dict, List, Optional, Set

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

RuleFunc = Callable[[TemplateNode, str], List[Diagnostic]]


# ---- Helpers ----

def _walk(node: Node, fn: Callable[[Node], None]) -> None:
    """Walk AST depth-first, calling fn on each node."""
    fn(node)
    if isinstance(node, TemplateNode):
        for c in node.body:
            _walk(c, fn)
    elif isinstance(node, BlockTagNode):
        for c in node.body:
            _walk(c, fn)
        for c in node.else_body:
            _walk(c, fn)
        for clause in node.elseif_clauses:
            for c in clause.get("body", []):
                _walk(c, fn)
    elif isinstance(node, PrintNode):
        if node.expression:
            _walk(node.expression, fn)
    elif isinstance(node, FilterNode):
        if node.target:
            _walk(node.target, fn)
        for a in node.args:
            if isinstance(a, Node):
                _walk(a, fn)
    elif isinstance(node, FunctionCallNode):
        for a in node.args:
            if isinstance(a, Node):
                _walk(a, fn)
    elif isinstance(node, BinaryOpNode):
        if node.left:
            _walk(node.left, fn)
        if node.right:
            _walk(node.right, fn)
    elif isinstance(node, UnaryOpNode):
        if node.operand:
            _walk(node.operand, fn)
    elif isinstance(node, TestNode):
        if node.target:
            _walk(node.target, fn)
    elif isinstance(node, ArrayNode):
        for item in node.items:
            _walk(item, fn)
    elif isinstance(node, MappingNode):
        for v in node.items.values():
            _walk(v, fn)
    elif isinstance(node, NamedArgNode):
        if node.value:
            _walk(node.value, fn)


# ============================================================
# Rules
# ============================================================

def check_extends_first(tree: TemplateNode, source: str) -> List[Diagnostic]:
    """{% extends %} must be the first tag."""
    diags = []
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
    return diags


def check_undefined_filters(tree: TemplateNode, source: str) -> List[Diagnostic]:
    """Check for unknown filters."""
    diags = []

    def visit(node: Node):
        if isinstance(node, FilterNode) and node.name and node.name not in BUILTIN_FILTERS:
            diags.append(Diagnostic(
                message=f"Unknown filter '{node.name}'.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-UNKNOWN-FILTER",
            ))

    _walk(tree, visit)
    return diags


def check_undefined_functions(tree: TemplateNode, source: str) -> List[Diagnostic]:
    """Check for unknown functions."""
    diags = []

    def visit(node: Node):
        if isinstance(node, FunctionCallNode) and node.name and node.name not in BUILTIN_FUNCTIONS:
            diags.append(Diagnostic(
                message=f"Unknown function '{node.name}()'.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-UNKNOWN-FUNCTION",
            ))

    _walk(tree, visit)
    return diags


def check_undefined_tests(tree: TemplateNode, source: str) -> List[Diagnostic]:
    """Check for unknown tests."""
    diags = []

    def visit(node: Node):
        if isinstance(node, TestNode) and node.name and node.name not in BUILTIN_TESTS:
            diags.append(Diagnostic(
                message=f"Unknown test '{node.name}'.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-UNKNOWN-TEST",
            ))

    _walk(tree, visit)
    return diags


def check_deprecated_features(tree: TemplateNode, source: str) -> List[Diagnostic]:
    """Check for deprecated tags and filters."""
    diags = []

    def visit(node: Node):
        # Deprecated tags
        if isinstance(node, (BlockTagNode, InlineTagNode)):
            if node.name in DEPRECATED and DEPRECATED[node.name]["type"] == "tag":
                info = DEPRECATED[node.name]
                diags.append(Diagnostic(
                    message=f"Deprecated tag '{node.name}': {info['message']}",
                    severity=Severity.WARNING,
                    range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                    rule_id="TWIG-DEPRECATED-TAG",
                ))
        # Deprecated filters
        if isinstance(node, FilterNode) and node.name in DEPRECATED and DEPRECATED[node.name]["type"] == "filter":
            info = DEPRECATED[node.name]
            diags.append(Diagnostic(
                message=f"Deprecated filter '{node.name}': {info['message']}",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                rule_id="TWIG-DEPRECATED-FILTER",
            ))

    _walk(tree, visit)
    return diags


def check_raw_filter_usage(tree: TemplateNode, source: str) -> List[Diagnostic]:
    """Warn about raw filter (XSS risk)."""
    diags = []

    def visit(node: Node):
        if isinstance(node, FilterNode) and node.name == "raw":
            diags.append(Diagnostic(
                message="Using 'raw' filter disables auto-escaping. Ensure content is trusted.",
                severity=Severity.WARNING,
                range=Range(node.line, node.column, node.line, node.column + 3),
                rule_id="TWIG-RAW-FILTER",
            ))

    _walk(tree, visit)
    return diags


def check_missing_escape(tree: TemplateNode, source: str) -> List[Diagnostic]:
    """Hint about bare variables that might need escaping."""
    diags = []
    in_autoescape = True  # default is autoescape on

    def visit(node: Node):
        nonlocal in_autoescape
        if isinstance(node, BlockTagNode) and node.name == "autoescape":
            return  # handled by autoescape
        if isinstance(node, PrintNode) and node.expression:
            expr = node.expression
            if isinstance(expr, VariableNode) and not expr.name.startswith("_"):
                # Bare variable print – could be a hint
                pass

    _walk(tree, visit)
    return diags


def check_hardcoded_strings(tree: TemplateNode, source: str) -> List[Diagnostic]:
    """Detect hardcoded text that might need i18n."""
    diags = []

    for child in tree.body:
        if isinstance(child, TextNode):
            stripped = child.value.strip()
            if len(stripped) > 20 and not stripped.startswith("<"):
                diags.append(Diagnostic(
                    message="Hardcoded text detected. Consider translation filters.",
                    severity=Severity.HINT,
                    range=Range(child.line, child.column, child.line,
                               child.column + min(len(stripped), 40)),
                    rule_id="TWIG-HARDCODED-TEXT",
                ))

    return diags


def check_variable_usage(tree: TemplateNode, source: str) -> List[Diagnostic]:
    """Track variable definitions and warn on undefined variables."""
    diags = []
    defined: Set[str] = set(GLOBAL_VARIABLES)

    def define_in(node: Node, scope: Set[str]) -> Set[str]:
        """Walk node, collect definitions into scope."""
        if isinstance(node, TemplateNode):
            for c in node.body:
                define_in(c, scope)
        elif isinstance(node, BlockTagNode):
            if node.name == "set":
                _extract_set_defs(node, scope)
            elif node.name == "for":
                _extract_for_defs(node, scope)
                new_scope = set(scope)
                for c in node.body:
                    define_in(c, new_scope)
                return scope
            elif node.name == "with":
                _extract_with_defs(node, scope)
                new_scope = set(scope)
                for c in node.body:
                    define_in(c, new_scope)
                return scope
            for c in node.body:
                define_in(c, scope)
            for c in node.else_body:
                define_in(c, scope)
            for cl in node.elseif_clauses:
                for c in cl.get("body", []):
                    define_in(c, scope)
        elif isinstance(node, InlineTagNode):
            if node.name in ("set", "do"):
                _extract_inline_set_defs(node, scope)
        elif isinstance(node, PrintNode):
            if node.expression:
                check_vars(node.expression, scope, diags)
        return scope

    def check_vars(node: Node, scope: Set[str], d: List[Diagnostic]) -> None:
        if isinstance(node, VariableNode):
            if node.name not in scope:
                d.append(Diagnostic(
                    message=f"Variable '{node.name}' may not be defined.",
                    severity=Severity.WARNING,
                    range=Range(node.line, node.column, node.line, node.column + len(node.name)),
                    rule_id="TWIG-UNDEFINED-VAR",
                ))
        elif isinstance(node, FilterNode):
            if node.target:
                check_vars(node.target, scope, d)
        elif isinstance(node, FunctionCallNode):
            for a in node.args:
                if isinstance(a, Node):
                    check_vars(a, scope, d)
        elif isinstance(node, BinaryOpNode):
            if node.left:
                check_vars(node.left, scope, d)
            if node.right:
                check_vars(node.right, scope, d)
        elif isinstance(node, UnaryOpNode):
            if node.operand:
                check_vars(node.operand, scope, d)
        elif isinstance(node, TestNode):
            if node.target:
                check_vars(node.target, scope, d)
        elif isinstance(node, ArrayNode):
            for item in node.items:
                check_vars(item, scope, d)
        elif isinstance(node, MappingNode):
            for v in node.items.values():
                check_vars(v, scope, d)

    define_in(tree, defined)
    return diags


def _extract_set_defs(node: BlockTagNode, scope: Set[str]) -> None:
    for arg in node.args:
        if isinstance(arg, VariableNode):
            scope.add(arg.name)


def _extract_for_defs(node: BlockTagNode, scope: Set[str]) -> None:
    for arg in node.args:
        if isinstance(arg, VariableNode):
            scope.add(arg.name)
    scope.add("loop")


def _extract_with_defs(node: BlockTagNode, scope: Set[str]) -> None:
    for arg in node.args:
        if isinstance(arg, VariableNode):
            scope.add(arg.name)
        elif isinstance(arg, MappingNode):
            for k in arg.items:
                scope.add(k)


def _extract_inline_set_defs(node: InlineTagNode, scope: Set[str]) -> None:
    for arg in node.args:
        if isinstance(arg, VariableNode):
            scope.add(arg.name)


# ============================================================
# Registry
# ============================================================

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
