"""Twig Parser – converts token stream into AST.

Uses Lexer's top-level tokens (TEXT, BLOCK_START/END, VAR_START/END, COMMENT)
and ExpressionTokenizer for content inside delimiters.
"""

from typing import Dict, List, Optional, Set

from .lexer import Lexer, ExpressionTokenizer, Token, TokenType
from .ast import (
    Node, TemplateNode, TextNode, PrintNode,
    BlockTagNode, InlineTagNode, CommentNode,
    VariableNode, LiteralNode, FunctionCallNode, FilterNode, TestNode,
    BinaryOpNode, UnaryOpNode, ArrayNode, MappingNode, NamedArgNode,
)
from .builtins import BLOCK_TAGS, END_TAG_MAP


class ParseError(Exception):
    def __init__(self, msg: str, line: int = 0, col: int = 0):
        super().__init__(f"[{line}:{col}] {msg}" if line else msg)
        self.line = line
        self.col = col


class Parser:
    """Parses Twig template source into AST."""

    def __init__(self, source: str):
        self.source = source
        self._lexer = Lexer(source)
        self._tokens: List[Token] = []
        self._pos = 0

    # ---- Public ----

    def parse(self) -> TemplateNode:
        self._tokens = self._lexer.tokenize()
        self._pos = 0
        return self._parse_template()

    # ---- Top-level ----

    def _parse_template(self) -> TemplateNode:
        node = TemplateNode(line=1, column=1)
        while not self._check(TokenType.EOF):
            child = self._parse_top_level()
            if child is not None:
                node.body.append(child)
        return node

    def _parse_top_level(self) -> Optional[Node]:
        tok = self._peek()
        if tok.type == TokenType.TEXT:
            self._adv()
            return TextNode(value=tok.value, line=tok.line, column=tok.column)
        if tok.type == TokenType.BLOCK_START:
            return self._parse_tag()
        if tok.type == TokenType.VAR_START:
            return self._parse_print()
        if tok.type == TokenType.COMMENT_START:
            return self._parse_comment()
        self._adv()
        return None

    # ---- Comments ----

    def _parse_comment(self) -> CommentNode:
        start = self._adv()  # COMMENT_START
        text_parts: List[str] = []
        depth = 1
        while not self._check(TokenType.EOF) and depth > 0:
            tok = self._peek()
            if tok.type == TokenType.COMMENT_START:
                depth += 1
                self._adv()
            elif tok.type == TokenType.COMMENT_END:
                depth -= 1
                if depth > 0:
                    text_parts.append(tok.value)
                self._adv()
            else:
                text_parts.append(tok.value)
                self._adv()
        return CommentNode(text="".join(text_parts).strip(),
                          line=start.line, column=start.column)

    # ---- Print ----

    def _parse_print(self) -> PrintNode:
        start = self._adv()  # VAR_START
        node = PrintNode(line=start.line, column=start.column)
        # Collect TEXT tokens until VAR_END, then tokenize with ExpressionTokenizer
        text_content = self._collect_text_until({TokenType.VAR_END})
        self._skip(TokenType.VAR_END)
        if text_content.strip():
            expr_tokens = ExpressionTokenizer(text_content, start.line, start.column).tokenize()
            if expr_tokens:
                try:
                    node.expression = self._expr_parse(expr_tokens)
                except ParseError:
                    pass
        return node

    # ---- Tags ----

    def _parse_tag(self) -> Optional[Node]:
        start = self._adv()  # BLOCK_START
        # Collect TEXT tokens until BLOCK_END, then tokenize with ExpressionTokenizer
        text_content = self._collect_text_until({TokenType.BLOCK_END})
        self._skip(TokenType.BLOCK_END)

        if not text_content.strip():
            return None

        header_tokens = ExpressionTokenizer(text_content, start.line, start.column).tokenize()
        if not header_tokens:
            return None

        # First token is tag name
        name_tok = header_tokens[0]
        if name_tok.type != TokenType.IDENTIFIER:
            return None
        tag_name = name_tok.value
        args = self._parse_tag_args(header_tokens[1:])

        # 'set' can be both inline ({% set x = 1 %}) and block ({% set %}...{% endset %})
        # For simplicity, treat as inline when there are arguments
        if tag_name == "set" and args:
            return InlineTagNode(name=tag_name, args=args,
                                line=start.line, column=start.column)

        if tag_name in BLOCK_TAGS:
            node = BlockTagNode(name=tag_name, args=args,
                               line=start.line, column=start.column)
            self._parse_block_body(tag_name, END_TAG_MAP.get(tag_name, f"end{tag_name}"), node)
            return node
        else:
            return InlineTagNode(name=tag_name, args=args,
                                line=start.line, column=start.column)

    def _parse_block_body(self, tag_name: str, end_name: str, node: BlockTagNode) -> None:
        """Parse the body of a block tag, respecting nesting."""
        while not self._check(TokenType.EOF):
            tok = self._peek()

            if tok.type == TokenType.TEXT:
                node.body.append(TextNode(value=tok.value, line=tok.line, column=tok.column))
                self._adv()
                continue

            if tok.type == TokenType.BLOCK_START:
                inner_line = tok.line
                inner_col = tok.column
                self._adv()  # consume BLOCK_START
                text_content = self._collect_text_until({TokenType.BLOCK_END})
                self._skip(TokenType.BLOCK_END)

                if not text_content.strip():
                    continue

                header = ExpressionTokenizer(text_content, inner_line, inner_col).tokenize()
                if not header or header[0].type != TokenType.IDENTIFIER:
                    continue

                inner_name = header[0].value

                # Check if this is our end tag
                if inner_name == end_name:
                    return

                # Handle else/elseif for if-tag
                if tag_name == "if" and not node.else_body and inner_name == "else":
                    node.else_body = self._parse_body_until(tag_name, end_name)
                    return
                if tag_name == "if" and inner_name == "elseif":
                    cond = self._parse_tag_args(header[1:])
                    clause_body = self._parse_body_until(tag_name, end_name)
                    node.elseif_clauses.append({"condition": cond, "body": clause_body})
                    return

                # Handle else for for-tag
                if tag_name == "for" and inner_name == "else":
                    node.else_body = self._parse_body_until(tag_name, end_name)
                    return

                # Nested block tag
                args = self._parse_tag_args(header[1:])
                if inner_name in BLOCK_TAGS:
                    inner_node = BlockTagNode(name=inner_name, args=args,
                                              line=header[0].line, column=header[0].column)
                    inner_end = END_TAG_MAP.get(inner_name, f"end{inner_name}")
                    self._parse_block_body(inner_name, inner_end, inner_node)
                    node.body.append(inner_node)
                else:
                    node.body.append(InlineTagNode(name=inner_name, args=args,
                                                   line=header[0].line, column=header[0].column))
                continue

            if tok.type == TokenType.VAR_START:
                node.body.append(self._parse_print())
                continue

            if tok.type == TokenType.COMMENT_START:
                node.body.append(self._parse_comment())
                continue

            self._adv()

    def _parse_body_until(self, tag_name: str, end_name: str) -> List[Node]:
        """Parse body until we hit the end tag (for else/elseif clauses)."""
        body: List[Node] = []
        while not self._check(TokenType.EOF):
            tok = self._peek()

            if tok.type == TokenType.TEXT:
                body.append(TextNode(value=tok.value, line=tok.line, column=tok.column))
                self._adv()
                continue

            if tok.type == TokenType.BLOCK_START:
                inner_line = tok.line
                inner_col = tok.column
                self._adv()
                text_content = self._collect_text_until({TokenType.BLOCK_END})
                self._skip(TokenType.BLOCK_END)

                if not text_content.strip():
                    continue

                header = ExpressionTokenizer(text_content, inner_line, inner_col).tokenize()
                if not header or header[0].type != TokenType.IDENTIFIER:
                    continue

                inner_name = header[0].value
                if inner_name == end_name:
                    return body

                # Nested
                args = self._parse_tag_args(header[1:])
                if inner_name in BLOCK_TAGS:
                    n = BlockTagNode(name=inner_name, args=args,
                                     line=header[0].line, column=header[0].column)
                    self._parse_block_body(inner_name, END_TAG_MAP.get(inner_name, f"end{inner_name}"), n)
                    body.append(n)
                else:
                    body.append(InlineTagNode(name=inner_name, args=args,
                                              line=header[0].line, column=header[0].column))
                continue

            if tok.type == TokenType.VAR_START:
                body.append(self._parse_print())
                continue

            if tok.type == TokenType.COMMENT_START:
                body.append(self._parse_comment())
                continue

            self._adv()
        return body

    # ---- Tag argument parsing ----

    def _parse_tag_args(self, tokens: List[Token]) -> List:
        """Parse tag arguments into simple AST nodes."""
        results = []
        for tok in tokens:
            if tok.type == TokenType.STRING:
                results.append(LiteralNode(value=tok.value, line=tok.line, column=tok.column))
            elif tok.type == TokenType.IDENTIFIER:
                results.append(VariableNode(name=tok.value, line=tok.line, column=tok.column))
            elif tok.type == TokenType.NUMBER:
                try:
                    v = float(tok.value) if "." in tok.value else int(tok.value)
                except ValueError:
                    v = tok.value
                results.append(LiteralNode(value=v, line=tok.line, column=tok.column))
            elif tok.type in (TokenType.BOOLEAN, TokenType.NULL):
                v = tok.value == "true" if tok.type == TokenType.BOOLEAN else None
                results.append(LiteralNode(value=v, line=tok.line, column=tok.column))
            # Skip operators and punctuation in tag args
        return results

    # ---- Helpers ----

    def _peek(self) -> Token:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return Token(TokenType.EOF, "", 1, 1)

    def _adv(self) -> Token:
        t = self._peek()
        self._pos += 1
        return t

    def _check(self, ttype: TokenType) -> bool:
        return self._peek().type == ttype

    def _skip(self, ttype: TokenType) -> bool:
        if self._check(ttype):
            self._adv()
            return True
        return False

    def _collect_text_until(self, stop: Set[TokenType]) -> str:
        """Collect TEXT token values until one of the stop types."""
        parts = []
        while not self._check(TokenType.EOF) and self._peek().type not in stop:
            tok = self._adv()
            parts.append(tok.value)
        return "".join(parts)

    # ---- Expression parsing (delegates to _ExpressionParser) ----

    def _expr_parse(self, tokens: List[Token]) -> Optional[Node]:
        if not tokens:
            return None
        # Remove EOF token if present
        tokens = [t for t in tokens if t.type != TokenType.EOF]
        if not tokens:
            return None
        return _ExpressionParser(tokens).parse()


# ============================================================
# Recursive Descent Expression Parser
# ============================================================

class _ExpressionParser:
    """Parses expression tokens into AST nodes."""

    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> Token:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else Token(TokenType.EOF, "", 1, 1)

    def _adv(self) -> Token:
        t = self._peek()
        self.pos += 1
        return t

    def _check(self, t: TokenType) -> bool:
        return self._peek().type == t

    def _match(self, t: TokenType) -> Optional[Token]:
        if self._check(t):
            return self._adv()
        return None

    def _match_val(self, *vals: str) -> bool:
        t = self._peek()
        return t.type == TokenType.IDENTIFIER and t.value in vals

    def parse(self) -> Optional[Node]:
        if self._check(TokenType.EOF):
            return None
        return self._ternary()

    # Ternary: a ? b : c  |  a ?: b
    def _ternary(self) -> Optional[Node]:
        node = self._null_coalesce()
        if node and self._match(TokenType.QUESTION):
            if self._match(TokenType.COLON):
                # a ?: b  (elvis)
                right = self._ternary()
                return BinaryOpNode(operator="?:", left=node, right=right,
                                   line=node.line, column=node.column)
            # a ? b : c
            true_expr = self._ternary()
            self._match(TokenType.COLON)
            false_expr = self._ternary()
            return BinaryOpNode(operator="?:", left=node,
                               right=BinaryOpNode(operator=":", left=true_expr, right=false_expr,
                                                  line=true_expr.line if true_expr else 1,
                                                  column=true_expr.column if true_expr else 1),
                               line=node.line, column=node.column)
        return node

    # Null-coalesce: a ?? b
    def _null_coalesce(self) -> Optional[Node]:
        node = self._or()
        # ?? is tokenized as two QUESTION tokens (not ideal but works)
        while self._check(TokenType.QUESTION):
            saved = self.pos
            self._adv()
            if self._check(TokenType.QUESTION):
                self._adv()
                right = self._or()
                node = BinaryOpNode(operator="??", left=node, right=right,
                                   line=node.line if node else 1, column=node.column if node else 1)
            else:
                self.pos = saved
                break
        return node

    def _or(self) -> Optional[Node]:
        node = self._and()
        while self._match_val("or"):
            right = self._and()
            node = BinaryOpNode(operator="or", left=node, right=right,
                               line=node.line if node else 1, column=node.column if node else 1)
        return node

    def _and(self) -> Optional[Node]:
        node = self._xor()
        while self._match_val("and"):
            right = self._xor()
            node = BinaryOpNode(operator="and", left=node, right=right,
                               line=node.line if node else 1, column=node.column if node else 1)
        return node

    def _xor(self) -> Optional[Node]:
        node = self._comparison()
        while self._match_val("xor"):
            right = self._comparison()
            node = BinaryOpNode(operator="xor", left=node, right=right,
                               line=node.line if node else 1, column=node.column if node else 1)
        return node

    def _comparison(self) -> Optional[Node]:
        node = self._concat()
        # Multi-word operators
        saved = self.pos
        words = []
        while self._peek().type == TokenType.IDENTIFIER:
            words.append(self._peek().value)
            self._adv()
        if words:
            op = " ".join(words)
            known = {"in", "not in", "is", "is not", "starts with", "ends with",
                     "matches", "has some", "has every"}
            if op in known:
                right = self._concat()
                return BinaryOpNode(operator=op, left=node, right=right,
                                   line=node.line if node else 1, column=node.column if node else 1)
            self.pos = saved
        # Single-char comparisons
        if self._peek().type == TokenType.OPERATOR and self._peek().value in \
                ("==", "!=", "<", ">", "<=", ">=", "<=>", "===", "!=="):
            op = self._adv().value
            right = self._concat()
            node = BinaryOpNode(operator=op, left=node, right=right,
                               line=node.line if node else 1, column=node.column if node else 1)
        return node

    def _concat(self) -> Optional[Node]:
        node = self._add_sub()
        while self._match(TokenType.CONCAT):
            right = self._add_sub()
            node = BinaryOpNode(operator="~", left=node, right=right,
                               line=node.line if node else 1, column=node.column if node else 1)
        return node

    def _add_sub(self) -> Optional[Node]:
        node = self._range()
        while self._peek().type == TokenType.OPERATOR and self._peek().value in ("+", "-"):
            op = self._adv().value
            right = self._range()
            node = BinaryOpNode(operator=op, left=node, right=right,
                               line=node.line if node else 1, column=node.column if node else 1)
        return node

    def _range(self) -> Optional[Node]:
        node = self._mul_div()
        if self._match(TokenType.RANGE):
            right = self._mul_div()
            node = BinaryOpNode(operator="..", left=node, right=right,
                               line=node.line if node else 1, column=node.column if node else 1)
        return node

    def _mul_div(self) -> Optional[Node]:
        node = self._unary()
        while self._peek().type == TokenType.OPERATOR and self._peek().value in ("*", "/", "//", "%", "**"):
            op = self._adv().value
            right = self._unary()
            node = BinaryOpNode(operator=op, left=node, right=right,
                               line=node.line if node else 1, column=node.column if node else 1)
        return node

    def _unary(self) -> Optional[Node]:
        if self._peek().type == TokenType.OPERATOR and self._peek().value in ("-", "+"):
            op = self._adv().value
            operand = self._unary()
            return UnaryOpNode(operator=op, operand=operand,
                              line=operand.line if operand else 1, column=operand.column if operand else 1)
        if self._match_val("not"):
            operand = self._unary()
            return UnaryOpNode(operator="not", operand=operand,
                              line=operand.line if operand else 1, column=operand.column if operand else 1)
        return self._filter_chain()

    def _filter_chain(self) -> Optional[Node]:
        node = self._primary()
        while node and self._match(TokenType.PIPE):
            name = ""
            if self._peek().type == TokenType.IDENTIFIER:
                name = self._adv().value
            args: List[Node] = []
            if self._match(TokenType.LPAREN):
                args = self._arg_list()
                self._match(TokenType.RPAREN)
            node = FilterNode(target=node, name=name, args=args,
                              line=node.line, column=node.column)
        return node

    def _primary(self) -> Optional[Node]:
        t = self._peek()

        if t.type == TokenType.STRING:
            self._adv()
            return LiteralNode(value=t.value, line=t.line, column=t.column)
        if t.type == TokenType.NUMBER:
            self._adv()
            try:
                v = float(t.value.replace("_", "")) if "." in t.value else int(t.value.replace("_", ""))
            except ValueError:
                v = t.value
            return LiteralNode(value=v, line=t.line, column=t.column)
        if t.type == TokenType.BOOLEAN:
            self._adv()
            return LiteralNode(value=t.value == "true", line=t.line, column=t.column)
        if t.type == TokenType.NULL:
            self._adv()
            return LiteralNode(value=None, line=t.line, column=t.column)
        if t.type == TokenType.IDENTIFIER:
            return self._var_or_call()
        if t.type == TokenType.LBRACKET:
            return self._array()
        if t.type == TokenType.LBRACE:
            return self._mapping()
        if t.type == TokenType.LPAREN:
            self._adv()
            n = self.parse()
            self._match(TokenType.RPAREN)
            return n

        self._adv()
        return None

    def _var_or_call(self) -> Optional[Node]:
        name_tok = self._adv()
        name = name_tok.value

        # Function call: name(...)
        if self._check(TokenType.LPAREN):
            self._adv()
            args = self._arg_list()
            self._match(TokenType.RPAREN)
            return FunctionCallNode(name=name, args=args,
                                    line=name_tok.line, column=name_tok.column)

        # Variable with optional attribute access
        node: Node = VariableNode(name=name, line=name_tok.line, column=name_tok.column)

        # Dot access: name.attr
        while self._match(TokenType.DOT):
            if self._peek().type == TokenType.IDENTIFIER:
                attr = self._adv()
                if isinstance(node, VariableNode):
                    node.attributes.append(attr.value)
                else:
                    node = BinaryOpNode(operator=".", left=node,
                                       right=VariableNode(name=attr.value, line=attr.line, column=attr.column),
                                       line=attr.line, column=attr.column)

        # Bracket access: name['key']
        while self._match(TokenType.LBRACKET):
            idx_tok = self._adv()
            self._match(TokenType.RBRACKET)
            if isinstance(node, VariableNode):
                node.attributes.append(f"[{idx_tok.value}]")

        # Test operator: name is test(args)
        if self._match_val("is"):
            negated = bool(self._match_val("not"))
            test_name = ""
            if self._peek().type == TokenType.IDENTIFIER:
                test_name = self._adv().value
                # Multi-word test
                if self._peek().type == TokenType.IDENTIFIER:
                    test_name += " " + self._adv().value
            test_args: List[Node] = []
            if self._match(TokenType.LPAREN):
                test_args = self._arg_list()
                self._match(TokenType.RPAREN)
            node = TestNode(target=node, name=test_name, negated=negated, args=test_args,
                           line=name_tok.line, column=name_tok.column)

        return node

    def _array(self) -> ArrayNode:
        start = self._adv()  # [
        items = []
        while not self._check(TokenType.RBRACKET) and not self._check(TokenType.EOF):
            self._match(TokenType.COMMA)
            if self._check(TokenType.RBRACKET):
                break
            n = self.parse()
            if n:
                items.append(n)
            self._match(TokenType.COMMA)
        self._match(TokenType.RBRACKET)
        return ArrayNode(items=items, line=start.line, column=start.column)

    def _mapping(self) -> MappingNode:
        start = self._adv()  # {
        items: Dict[str, Node] = {}
        while not self._check(TokenType.RBRACE) and not self._check(TokenType.EOF):
            self._match(TokenType.COMMA)
            if self._check(TokenType.RBRACE):
                break
            key_node = self.parse()
            if key_node is None:
                break
            key_str = ""
            if isinstance(key_node, VariableNode):
                key_str = key_node.name
            elif isinstance(key_node, LiteralNode):
                key_str = str(key_node.value)

            if self._match(TokenType.COLON):
                val = self.parse()
                if val and key_str:
                    items[key_str] = val
            else:
                # Shorthand {key} -> {'key': key}
                if key_str:
                    items[key_str] = VariableNode(name=key_str, line=start.line, column=start.column)
            self._match(TokenType.COMMA)
        self._match(TokenType.RBRACE)
        return MappingNode(items=items, line=start.line, column=start.column)

    def _arg_list(self) -> List[Node]:
        args = []
        while not self._check(TokenType.RPAREN) and not self._check(TokenType.EOF):
            self._match(TokenType.COMMA)
            if self._check(TokenType.RPAREN):
                break
            # Named arg: name: value
            saved = self.pos
            if self._peek().type == TokenType.IDENTIFIER:
                name_tok = self._adv()
                if self._match(TokenType.COLON) or (self._peek().type == TokenType.ASSIGN):
                    self._adv()
                    val = self.parse()
                    if val:
                        args.append(NamedArgNode(name=name_tok.value, value=val,
                                                 line=name_tok.line, column=name_tok.column))
                    self._match(TokenType.COMMA)
                    continue
                self.pos = saved
            n = self.parse()
            if n:
                args.append(n)
            self._match(TokenType.COMMA)
        return args
