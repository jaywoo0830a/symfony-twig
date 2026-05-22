"""AST nodes for Twig templates — immutable, algebraic data types.

All nodes are frozen dataclasses. Collections use `tuple[...]` for immutability.
Use `replace()` to create modified copies.
"""

from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Optional, Sequence, Tuple, Union


@dataclass(frozen=True)
class Node:
    """Base node with source location."""
    line: int = 0
    column: int = 0

    def __repr__(self) -> str:
        return f"{type(self).__name__}@{self.line}"


# ═══════════════════════════════════════════════════════════════════════
# 1. Template-level nodes
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class TemplateNode(Node):
    """Root node — the whole template."""
    body: Tuple[Node, ...] = ()
    line: int = 1
    column: int = 1

    @staticmethod
    def create(body: Sequence[Node] = ()) -> TemplateNode:
        return TemplateNode(body=tuple(body))


@dataclass(frozen=True)
class TextNode(Node):
    """Raw text content."""
    value: str = ""


@dataclass(frozen=True)
class PrintNode(Node):
    """{{ expr }} — output expression."""
    expression: Optional[Node] = None


@dataclass(frozen=True)
class CommentNode(Node):
    """{# comment #}."""
    text: str = ""


@dataclass(frozen=True)
class BlockTagNode(Node):
    """{% tag %} body {% endtag %} with optional else/elseif branches."""
    name: str = ""
    args: Tuple[Node, ...] = ()
    body: Tuple[Node, ...] = ()
    else_body: Tuple[Node, ...] = ()
    elseif_clauses: Tuple[Mapping[str, Any], ...] = ()

    @staticmethod
    def create(
        name: str,
        args: Sequence[Node] = (),
        body: Sequence[Node] = (),
        line: int = 0,
        column: int = 0,
    ) -> BlockTagNode:
        return BlockTagNode(
            name=name, args=tuple(args), body=tuple(body),
            line=line, column=column,
        )

    def with_else_body(self, body: Sequence[Node]) -> BlockTagNode:
        return replace(self, else_body=tuple(body))

    def with_elseif(self, clauses: Sequence[Mapping[str, Any]]) -> BlockTagNode:
        return replace(self, elseif_clauses=tuple(clauses))


@dataclass(frozen=True)
class InlineTagNode(Node):
    """{% tag %} — tag with no body."""
    name: str = ""
    args: Tuple[Node, ...] = ()

    @staticmethod
    def create(name: str, args: Sequence[Node] = (), line: int = 0, column: int = 0) -> InlineTagNode:
        return InlineTagNode(name=name, args=tuple(args), line=line, column=column)


# ═══════════════════════════════════════════════════════════════════════
# 2. Expression nodes
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class VariableNode(Node):
    """Variable reference: name or name.attr.subattr."""
    name: str = ""
    attributes: Tuple[str, ...] = ()

    @staticmethod
    def create(name: str, attributes: Sequence[str] = (), line: int = 0, column: int = 0) -> VariableNode:
        return VariableNode(name=name, attributes=tuple(attributes), line=line, column=column)

    @property
    def full_path(self) -> str:
        return self.name + "".join(f".{a}" for a in self.attributes)


@dataclass(frozen=True)
class LiteralNode(Node):
    """Literal value: string, number, boolean, null, array, mapping."""
    value: Any = None


@dataclass(frozen=True)
class FunctionCallNode(Node):
    """Function call: fn(args)."""
    name: str = ""
    args: Tuple[Node, ...] = ()

    @staticmethod
    def create(name: str, args: Sequence[Node] = (), line: int = 0, column: int = 0) -> FunctionCallNode:
        return FunctionCallNode(name=name, args=tuple(args), line=line, column=column)


@dataclass(frozen=True)
class FilterNode(Node):
    """Filter: target|filter(args)."""
    target: Optional[Node] = None
    name: str = ""
    args: Tuple[Node, ...] = ()

    @staticmethod
    def create(
        target: Optional[Node], name: str, args: Sequence[Node] = (),
        line: int = 0, column: int = 0,
    ) -> FilterNode:
        return FilterNode(target=target, name=name, args=tuple(args), line=line, column=column)


@dataclass(frozen=True)
class TestNode(Node):
    """Test: expr is test(args) or expr is not test(args)."""
    target: Optional[Node] = None
    name: str = ""
    negated: bool = False
    args: Tuple[Node, ...] = ()

    @staticmethod
    def create(
        target: Optional[Node], name: str, negated: bool = False,
        args: Sequence[Node] = (), line: int = 0, column: int = 0,
    ) -> TestNode:
        return TestNode(target=target, name=name, negated=negated, args=tuple(args), line=line, column=column)


@dataclass(frozen=True)
class BinaryOpNode(Node):
    """Binary operation: left op right."""
    operator: str = ""
    left: Optional[Node] = None
    right: Optional[Node] = None


@dataclass(frozen=True)
class UnaryOpNode(Node):
    """Unary operation: op operand."""
    operator: str = ""
    operand: Optional[Node] = None


@dataclass(frozen=True)
class ArrayNode(Node):
    """Sequence literal: [item, ...]."""
    items: Tuple[Node, ...] = ()

    @staticmethod
    def create(items: Sequence[Node] = (), line: int = 0, column: int = 0) -> ArrayNode:
        return ArrayNode(items=tuple(items), line=line, column=column)


@dataclass(frozen=True)
class MappingNode(Node):
    """Mapping literal: {key: value, ...}."""
    items: Mapping[str, Node] = field(default_factory=dict)

    @staticmethod
    def create(items: Mapping[str, Node] | None = None, line: int = 0, column: int = 0) -> MappingNode:
        return MappingNode(items=dict(items) if items else {}, line=line, column=column)


@dataclass(frozen=True)
class NamedArgNode(Node):
    """Named argument: name=value or name: value."""
    name: str = ""
    value: Optional[Node] = None


# ═══════════════════════════════════════════════════════════════════════
# 3. Type aliases
# ═══════════════════════════════════════════════════════════════════════

Expression = Union[
    VariableNode, LiteralNode, FunctionCallNode, FilterNode,
    TestNode, BinaryOpNode, UnaryOpNode, ArrayNode, MappingNode,
    NamedArgNode,
]

AnyNode = Union[
    TemplateNode, TextNode, PrintNode, CommentNode,
    BlockTagNode, InlineTagNode, Expression,
]
