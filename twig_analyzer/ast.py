"""AST nodes for Twig templates – plain classes for simplicity."""

from typing import Any, Dict, List


class Node:
    """Base node."""
    def __init__(self, line: int = 0, column: int = 0):
        self.line = line
        self.column = column

    def __repr__(self):
        return f"{self.__class__.__name__}@{self.line}"


class TemplateNode(Node):
    """Root node."""
    def __init__(self, body: List[Node] = None, line: int = 1, column: int = 1):
        super().__init__(line, column)
        self.body = body or []


class TextNode(Node):
    """Raw text."""
    def __init__(self, value: str = "", line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.value = value


class PrintNode(Node):
    """{{ expr }}"""
    def __init__(self, expression: Node = None, line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.expression = expression


class BlockTagNode(Node):
    """{% tag %} body {% endtag %}"""
    def __init__(self, name: str = "", args: List = None, body: List[Node] = None,
                 line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.name = name
        self.args = args or []
        self.body = body or []
        self.else_body: List[Node] = []
        self.elseif_clauses: List[dict] = []


class InlineTagNode(Node):
    """{% tag %} (no body)"""
    def __init__(self, name: str = "", args: List = None, line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.name = name
        self.args = args or []


class CommentNode(Node):
    """{# comment #}"""
    def __init__(self, text: str = "", line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.text = text


# ---- Expression Nodes ----

class VariableNode(Node):
    """Variable reference: name or name.attr.attr"""
    def __init__(self, name: str = "", attributes: List[str] = None,
                 line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.name = name
        self.attributes = attributes or []

    @property
    def full_path(self) -> str:
        return self.name + "".join(f".{a}" for a in self.attributes)


class LiteralNode(Node):
    """Literal value: string, number, boolean, null, array"""
    def __init__(self, value: Any = None, line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.value = value


class FunctionCallNode(Node):
    """Function call: fn(args)"""
    def __init__(self, name: str = "", args: List = None,
                 line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.name = name
        self.args = args or []


class FilterNode(Node):
    """Filter: expr|filter(args)"""
    def __init__(self, target: Node = None, name: str = "", args: List = None,
                 line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.target = target
        self.name = name
        self.args = args or []


class TestNode(Node):
    """Test: expr is test(args)"""
    def __init__(self, target: Node = None, name: str = "", negated: bool = False,
                 args: List = None, line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.target = target
        self.name = name
        self.negated = negated
        self.args = args or []


class BinaryOpNode(Node):
    """Binary operation: left op right"""
    def __init__(self, operator: str = "", left: Node = None, right: Node = None,
                 line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.operator = operator
        self.left = left
        self.right = right


class UnaryOpNode(Node):
    """Unary operation: op expr"""
    def __init__(self, operator: str = "", operand: Node = None,
                 line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.operator = operator
        self.operand = operand


class ArrayNode(Node):
    """Sequence literal: [expr, ...]"""
    def __init__(self, items: List[Node] = None, line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.items = items or []


class MappingNode(Node):
    """Mapping literal: {key: value, ...}"""
    def __init__(self, items: Dict[str, Node] = None, line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.items = items or {}


class NamedArgNode(Node):
    """Named argument: name: value"""
    def __init__(self, name: str = "", value: Node = None,
                 line: int = 0, column: int = 0):
        super().__init__(line, column)
        self.name = name
        self.value = value
