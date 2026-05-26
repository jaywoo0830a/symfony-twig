"""Twig Parser — recursive descent, pure functions.

Converts token stream → immutable AST (TemplateNode).
All parsing functions return AST nodes. Errors raise ParseError.
"""

from __future__ import annotations
import re
from dataclasses import replace
from typing import List, Optional, Sequence, Tuple

from .lexer import TokenType, Token, tokenize, ExpressionTokenizer
from .ast import (
    Node, TemplateNode, TextNode, PrintNode, CommentNode,
    BlockTagNode, InlineTagNode, VariableNode, LiteralNode,
    FunctionCallNode, FilterNode, TestNode, BinaryOpNode,
    UnaryOpNode, ArrayNode, MappingNode, NamedArgNode,
)


class ParseError(Exception):
    def __init__(self, message: str, line: int = 0, column: int = 0):
        super().__init__(message)
        self.line = line
        self.column = column

    def __str__(self) -> str:
        return f"Parse error at {self.line}:{self.column}: {super().__str__()}"


# ═══════════════════════════════════════════════════════════════════════
# 1. Token stream (read-only cursor)
# ═══════════════════════════════════════════════════════════════════════

class Stream:
    """Immutable view over a token list + cursor position."""
    __slots__ = ('_tokens', '_pos')

    def __init__(self, tokens: Sequence[Token], pos: int = 0):
        self._tokens = tuple(tokens)
        self._pos = pos

    @property
    def current(self) -> Token:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else Token(TokenType.EOF, '', 0, 0)

    @property
    def peek(self) -> Token:
        return self._tokens[self._pos + 1] if self._pos + 1 < len(self._tokens) else Token(TokenType.EOF, '', 0, 0)

    @property
    def done(self) -> bool:
        return self._pos >= len(self._tokens) or self.current.type == TokenType.EOF

    @property
    def pos(self) -> int:
        return self._pos

    def at(self, offset: int) -> Token:
        idx = self._pos + offset
        return self._tokens[idx] if 0 <= idx < len(self._tokens) else Token(TokenType.EOF, '', 0, 0)

    def advance(self, n: int = 1) -> Stream:
        return Stream(self._tokens, self._pos + n)

    def expect(self, ttype: TokenType) -> Tuple[Stream, Token]:
        tok = self.current
        if tok.type != ttype:
            raise ParseError(f"Expected {ttype.name}, got {tok.type.name}", tok.line, tok.column)
        return self.advance(), tok

    def match(self, ttype: TokenType) -> Optional[Tuple[Stream, Token]]:
        if self.current.type == ttype:
            return self.advance(), self.current
        return None


# ═══════════════════════════════════════════════════════════════════════
# 2. Parser entry point
# ═══════════════════════════════════════════════════════════════════════

def parse(source: str) -> TemplateNode:
    """Parse a Twig template source into an AST. Pure: str → TemplateNode."""
    tokens = tokenize(source)
    stream = Stream(tokens)
    return _parse_template(stream)


def _parse_template(stream: Stream) -> TemplateNode:
    body: List[Node] = []
    s = stream

    while not s.done:
        tok = s.current

        if tok.type == TokenType.TEXT:
            body.append(TextNode(value=tok.value, line=tok.line, column=tok.column))
            s = s.advance()
        elif tok.type == TokenType.VAR_START:
            node, s = _parse_print(s)
            body.append(node)
        elif tok.type == TokenType.BLOCK_START:
            node, s = _parse_block(s)
            body.append(node)
        elif tok.type == TokenType.COMMENT_START:
            body.append(CommentNode(text=tok.value, line=tok.line, column=tok.column))
            s = s.advance()
        else:
            s = s.advance()  # Skip unknown

    return TemplateNode.create(body)


# ═══════════════════════════════════════════════════════════════════════
# 3. Print node: {{ expr }}
# ═══════════════════════════════════════════════════════════════════════

def _parse_print(stream: Stream) -> Tuple[PrintNode, Stream]:
    tok = stream.current
    raw_inner = tok.value[2:-2]  # Remove {{ and }} but keep whitespace
    inner = raw_inner.strip()
    line, col = tok.line, tok.column + 2

    if not inner:
        return PrintNode(line=line, column=col), stream.advance()

    # The expression tokenizer always starts at line=1, col=1.
    # Offset positions by the actual print location minus the tokenizer origin.
    # Account for leading whitespace removed by .strip()
    leading_spaces = len(raw_inner) - len(raw_inner.lstrip())
    col_offset = col + leading_spaces - 1
    line_offset = line - 1

    expr_tokens = ExpressionTokenizer.tokenize(inner)
    expr_node, _ = _parse_expression(Stream(expr_tokens)) if expr_tokens else (None, None)
    if expr_node is not None:
        expr_node = _offset_node(expr_node, line_offset, col_offset)
    return PrintNode(expression=expr_node, line=line, column=col), stream.advance()


def _offset_node(node: Node, dl: int, dc: int) -> Node:
    """Offset all positions in a node tree by (dl lines, dc columns)."""
    if node is None:
        return None
    node = replace(node, line=node.line + dl, column=node.column + dc)
    # Recurse into children
    if isinstance(node, PrintNode) and node.expression:
        node = replace(node, expression=_offset_node(node.expression, dl, dc))
    elif isinstance(node, FilterNode):
        if node.target:
            node = replace(node, target=_offset_node(node.target, dl, dc))
        node = replace(node, args=tuple(_offset_node(a, dl, dc) for a in node.args))
    elif isinstance(node, FunctionCallNode):
        node = replace(node, args=tuple(_offset_node(a, dl, dc) for a in node.args))
    elif isinstance(node, TestNode):
        if node.target:
            node = replace(node, target=_offset_node(node.target, dl, dc))
        node = replace(node, args=tuple(_offset_node(a, dl, dc) for a in node.args))
    elif isinstance(node, BinaryOpNode):
        if node.left:
            node = replace(node, left=_offset_node(node.left, dl, dc))
        if node.right:
            node = replace(node, right=_offset_node(node.right, dl, dc))
    elif isinstance(node, UnaryOpNode) and node.operand:
        node = replace(node, operand=_offset_node(node.operand, dl, dc))
    elif isinstance(node, ArrayNode):
        node = replace(node, items=tuple(_offset_node(i, dl, dc) for i in node.items))
    elif isinstance(node, MappingNode):
        node = replace(node, items={k: _offset_node(v, dl, dc) for k, v in node.items.items()})
    elif isinstance(node, NamedArgNode) and node.value:
        node = replace(node, value=_offset_node(node.value, dl, dc))
    return node


# ═══════════════════════════════════════════════════════════════════════
# 4. Block tag: {% tag %} body {% endtag %}
# ═══════════════════════════════════════════════════════════════════════

_BLOCK_TAGS = frozenset({
    "apply", "autoescape", "block", "cache", "deprecated",
    "embed", "for", "guard", "if", "macro", "sandbox",
    "verbatim", "with",
    # Symfony block tags
    "trans", "stopwatch",
})

_INLINE_TAGS = frozenset({
    "do", "extends", "flush", "from", "import", "include", "use",
    # Symfony inline tags
    "form_theme", "trans_default_domain",
})

# Tags that can be either block or inline depending on content
_DUAL_TAGS = frozenset({"set", "types"})

_ALL_BLOCK_TAGS = _BLOCK_TAGS | _DUAL_TAGS


def _parse_block(stream: Stream) -> Tuple[Node, Stream]:
    tok = stream.current
    inner = tok.value[2:-2].strip()  # Remove {% and %}
    line, col = tok.line, tok.column + 2

    # Extract tag name
    parts = inner.split(None, 1)
    tag_name = parts[0] if parts else ""
    tag_args_str = parts[1] if len(parts) > 1 else ""

    # Dual tags: check if this is inline (has content before %}) or block
    if tag_name in _DUAL_TAGS and tag_args_str and not tok.value.rstrip().endswith(f"end{tag_name} %}}}}"):
        # Inline usage: {% set x = 1 %} (has content between tag name and %})
        # Parse the variable name for set tags
        args: List[Node] = []
        if tag_name == "set" and tag_args_str:
            # Extract variable name before '='
            var_match = re.match(r'(\w+)', tag_args_str)
            if var_match:
                args.append(LiteralNode(value=var_match.group(1), line=line, column=col))
        return InlineTagNode.create(name=tag_name, args=args, line=line, column=col), stream.advance()

    # Block tags with bodies
    if tag_name in _ALL_BLOCK_TAGS:
        return _parse_block_tag(stream, tag_name, tag_args_str, line, col)

    # Inline tags (no body)
    return InlineTagNode.create(name=tag_name, line=line, column=col), stream.advance()


def _parse_block_tag(stream: Stream, tag_name: str, args_str: str, line: int, col: int) -> Tuple[BlockTagNode, Stream]:
    end_tag = f"end{tag_name}"
    body: List[Node] = []
    else_body: List[Node] = []
    elseif_clauses: List[dict] = []
    s = stream.advance()
    in_else = False
    current_target = body

    while not s.done:
        tok = s.current

        if tok.type == TokenType.BLOCK_START:
            inner = tok.value[2:-2].strip()
            inner_parts = inner.split(None, 1)
            inner_name = inner_parts[0] if inner_parts else ""

            if inner_name == end_tag:
                s = s.advance()
                break
            elif inner_name in ("else", "elseif") and tag_name in ("if", "for"):
                if inner_name == "else":
                    in_else = True
                    current_target = else_body
                else:
                    clause = {"body": [], "condition": inner_parts[1] if len(inner_parts) > 1 else ""}
                    elseif_clauses.append(clause)
                    current_target = clause["body"]
                s = s.advance()
                continue
            elif inner_name in _ALL_BLOCK_TAGS:
                node, s = _parse_block_tag(s, inner_name, inner_parts[1] if len(inner_parts) > 1 else "", tok.line, tok.column + 2)
                current_target.append(node)
                continue
            elif inner_name in _INLINE_TAGS:
                current_target.append(InlineTagNode.create(name=inner_name, line=tok.line, column=tok.column + 2))
                s = s.advance()
                continue

        if tok.type == TokenType.VAR_START:
            node, s = _parse_print(s)
            current_target.append(node)
            continue

        if tok.type == TokenType.COMMENT_START:
            current_target.append(CommentNode(text=tok.value, line=tok.line, column=tok.column))
            s = s.advance()
            continue

        if tok.type == TokenType.TEXT:
            current_target.append(TextNode(value=tok.value, line=tok.line, column=tok.column))
            s = s.advance()
            continue

        s = s.advance()

    node = BlockTagNode.create(name=tag_name, body=body, line=line, column=col)
    if else_body:
        node = node.with_else_body(else_body)
    if elseif_clauses:
        node = node.with_elseif(elseif_clauses)
    return node, s


# ═══════════════════════════════════════════════════════════════════════
# 5. Expression parser
# ═══════════════════════════════════════════════════════════════════════

def _parse_expression(stream: Stream) -> Tuple[Optional[Node], Stream]:
    """Parse a Twig expression. Returns (node, remaining_stream)."""
    if stream.done:
        return None, stream

    left, stream = _parse_primary(stream)
    if left is None:
        return None, stream

    result, stream = _parse_infix(stream, left, 0)
    return result, stream


def _parse_primary(stream: Stream) -> Tuple[Optional[Node], Stream]:
    tok = stream.current

    # String literal
    if tok.type == TokenType.STRING:
        val = tok.value[1:-1]  # strip quotes
        return LiteralNode(value=val, line=tok.line, column=tok.column), stream.advance()

    # Number
    if tok.type == TokenType.NUMBER:
        val = float(tok.value) if '.' in tok.value else int(tok.value.replace('_', ''))
        return LiteralNode(value=val, line=tok.line, column=tok.column), stream.advance()

    # Boolean / null
    if tok.type in (TokenType.BOOLEAN, TokenType.NULL):
        val = {"true": True, "false": False, "null": None, "none": None}.get(tok.value.lower(), None)
        return LiteralNode(value=val, line=tok.line, column=tok.column), stream.advance()

    # Identifier → variable or function call
    if tok.type == TokenType.IDENTIFIER:
        name = tok.value
        stream = stream.advance()

        # Function call: name(args)
        if stream.current.type == TokenType.LPAREN:
            args, stream = _parse_args(stream)
            return FunctionCallNode.create(name=name, args=args, line=tok.line, column=tok.column), stream

        # Variable with attributes
        attrs: List[str] = []
        while stream.current.type == TokenType.DOT:
            stream = stream.advance()
            attr_tok = stream.current
            if attr_tok.type == TokenType.IDENTIFIER:
                attrs.append(attr_tok.value)
                stream = stream.advance()
            else:
                break

        return VariableNode.create(name=name, attributes=attrs, line=tok.line, column=tok.column), stream

    # Sequence: [items]
    if tok.type == TokenType.LBRACKET:
        items, stream = _parse_sequence(stream)
        return ArrayNode.create(items=items, line=tok.line, column=tok.column), stream

    # Mapping: {key: value, ...}
    if tok.type == TokenType.LBRACE:
        items, stream = _parse_mapping(stream)
        return MappingNode.create(items=items, line=tok.line, column=tok.column), stream

    return None, stream


def _parse_args(stream: Stream) -> Tuple[Tuple[Node, ...], Stream]:
    """Parse function call arguments: (arg1, arg2, name=val)."""
    s, _ = stream.expect(TokenType.LPAREN)

    if s.current.type == TokenType.RPAREN:
        return (), s.advance()

    args: List[Node] = []
    while True:
        expr, s = _parse_primary(s)
        if expr is not None:
            # Named arg: name=value or name:value
            if s.current.type in (TokenType.COLON, TokenType.OPERATOR) and s.current.value == '=':
                name = expr.full_path if hasattr(expr, 'full_path') else getattr(expr, 'name', str(expr.value) if hasattr(expr, 'value') else '')
                s = s.advance()
                val, s = _parse_primary(s)
                args.append(NamedArgNode(name=name, value=val, line=expr.line, column=expr.column))
            else:
                args.append(expr)

            # More arguments
            s = _parse_infix_after_arg(s, expr)

        if s.current.type == TokenType.RPAREN:
            return tuple(args), s.advance()

        if s.current.type == TokenType.COMMA:
            s = s.advance()
        else:
            break

    return tuple(args), s


def _parse_infix_after_arg(stream: Stream, left: Node) -> Stream:
    """Continue parsing after an argument (filters, binary ops)."""
    s = stream
    while True:
        tok = s.current

        # Filter: |
        if tok.type == TokenType.PIPE:
            s = s.advance()
            fn_tok = s.current
            if fn_tok.type == TokenType.IDENTIFIER:
                s = s.advance()
                # Filter args
                filter_args: Tuple[Node, ...] = ()
                if s.current.type == TokenType.LPAREN:
                    filter_args, s = _parse_args(s)
                # Note: left is already consumed; this is for the expression tree
            continue

        # Binary operators
        if tok.type in (TokenType.OPERATOR, TokenType.DOT, TokenType.PIPE):
            s = s.advance()
            continue

        break

    return s


def _parse_infix(stream: Stream, left: Node, min_prec: int) -> Tuple[Node, Stream]:
    """Parse infix operators. Returns (result_node, remaining_stream)."""
    result = left
    s = stream

    while True:
        tok = s.current

        # Filter: |
        if tok.type == TokenType.PIPE:
            s = s.advance()
            fn_name = ""
            fn_args: Tuple[Node, ...] = ()
            if s.current.type == TokenType.IDENTIFIER:
                fn_name = s.current.value
                s = s.advance()
                if s.current.type == TokenType.LPAREN:
                    fn_args, s = _parse_args(s)
            result = FilterNode.create(target=result, name=fn_name, args=fn_args, line=tok.line, column=tok.column)
            continue

        # Test: is / is not
        if tok.type == TokenType.OPERATOR and tok.value in ('is', 'is not'):
            negated = tok.value == 'is not'
            s = s.advance()
            test_name = ""
            test_args: Tuple[Node, ...] = ()
            if s.current.type == TokenType.IDENTIFIER:
                test_name = s.current.value
                s = s.advance()
                if s.current.type == TokenType.LPAREN:
                    test_args, s = _parse_args(s)
            elif s.current.type == TokenType.OPERATOR:
                # Multi-word test like "divisible by"
                test_name = s.current.value
                s = s.advance()
            result = TestNode.create(target=result, name=test_name, negated=negated, args=test_args, line=tok.line, column=tok.column)
            continue

        # Dot access
        if tok.type == TokenType.DOT:
            s = s.advance()
            if s.current.type == TokenType.IDENTIFIER:
                attr = s.current.value
                s = s.advance()
                # Convert result to have attr — create VariableNode if needed
                if isinstance(result, VariableNode):
                    result = VariableNode.create(name=result.name, attributes=result.attributes + (attr,), line=result.line, column=result.column)
            continue

        # Assignment
        if tok.type == TokenType.OPERATOR and tok.value == '=':
            s = s.advance()
            rhs, s = _parse_primary(s)
            if rhs is not None:
                result = BinaryOpNode(operator='=', left=result, right=rhs, line=tok.line, column=tok.column)
            continue

        # Other binary operators
        if tok.type in (TokenType.OPERATOR, TokenType.CONCAT):
            op = tok.value
            prec = _precedence(op)
            if prec <= min_prec:
                break
            s = s.advance()
            rhs, s = _parse_primary(s)
            if rhs is not None:
                rhs, s = _parse_infix(s, rhs, prec)
                result = BinaryOpNode(operator=op, left=result, right=rhs, line=tok.line, column=tok.column)
            continue

        break

    return result, s


def _precedence(op: str) -> int:
    return {
        '=': 0, '?:': 5, 'or': 10, 'xor': 12, 'and': 15,
        'b-or': 16, 'b-xor': 17, 'b-and': 18,
        '==': 20, '!=': 20, '<': 20, '>': 20, '<=': 20, '>=': 20,
        '===': 20, '!==': 20, 'in': 20, 'not in': 20, 'matches': 20,
        'starts with': 20, 'ends with': 20, 'has some': 20, 'has every': 20,
        '..': 25, '+': 30, '-': 30, '~': 27,
        'not': 70, '*': 60, '/': 60, '//': 60, '%': 60, '**': 200,
        'is': 100, 'is not': 100,
    }.get(op, 0)


def _parse_sequence(stream: Stream) -> Tuple[Tuple[Node, ...], Stream]:
    s, _ = stream.expect(TokenType.LBRACKET)
    items: List[Node] = []

    while s.current.type != TokenType.RBRACKET and not s.done:
        expr, s = _parse_expression(s)
        if expr is not None:
            items.append(expr)
        if s.current.type == TokenType.COMMA:
            s = s.advance()
    if s.current.type == TokenType.RBRACKET:
        s = s.advance()
    return tuple(items), s


def _parse_mapping(stream: Stream) -> Tuple[dict, Stream]:
    s, _ = stream.expect(TokenType.LBRACE)
    items: dict = {}

    while s.current.type != TokenType.RBRACE and not s.done:
        key_node, s = _parse_expression(s)
        key: str = ""
        if key_node is not None:
            if isinstance(key_node, LiteralNode):
                key = str(key_node.value) if key_node.value is not None else ""
            elif isinstance(key_node, VariableNode):
                key = key_node.name

        if s.current.type in (TokenType.COLON, TokenType.OPERATOR) and s.current.value in (':', '='):
            s = s.advance()
        elif s.current.type == TokenType.COMMA or s.current.type == TokenType.RBRACE:
            # Shorthand: {name} → {'name': name}
            items[key] = key_node
            if s.current.type == TokenType.COMMA:
                s = s.advance()
            continue

        val_node, s = _parse_expression(s)
        if val_node is not None:
            items[key] = val_node

        if s.current.type == TokenType.COMMA:
            s = s.advance()

    if s.current.type == TokenType.RBRACE:
        s = s.advance()
    return items, s
