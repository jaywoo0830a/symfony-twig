"""Twig Lexer — pure tokenizer, no mutable state.

Two-level tokenizer:
1. tokenize(source) → Tuple[Token, ...] — splits source into delimiters and text
2. ExpressionTokenizer.tokenize(text) → Tuple[Token, ...] — tokenizes expressions
"""

from __future__ import annotations
from enum import Enum, auto
from typing import List, NamedTuple, Tuple


class TokenType(Enum):
    TEXT = auto()
    BLOCK_START = auto(); BLOCK_END = auto()
    VAR_START = auto();   VAR_END = auto()
    COMMENT_START = auto(); COMMENT_END = auto()
    IDENTIFIER = auto(); STRING = auto(); NUMBER = auto()
    BOOLEAN = auto(); NULL = auto()
    OPERATOR = auto(); DOT = auto(); PIPE = auto()
    RANGE = auto(); CONCAT = auto()
    QUESTION = auto(); COLON = auto(); COMMA = auto()
    LPAREN = auto(); RPAREN = auto()
    LBRACKET = auto(); RBRACKET = auto()
    LBRACE = auto(); RBRACE = auto()
    EOF = auto()


class Token(NamedTuple):
    type: TokenType
    value: str
    line: int
    column: int

    def __repr__(self) -> str:
        return f"<{self.type.name}:{self.value!r}@{self.line}:{self.column}>"


_KEYWORDS = {"true": TokenType.BOOLEAN, "false": TokenType.BOOLEAN,
             "null": TokenType.NULL, "none": TokenType.NULL}


# ═══════════════════════════════════════════════════════════════════════
# 1. Template lexer: source → tokens
# ═══════════════════════════════════════════════════════════════════════

def tokenize(source: str) -> Tuple[Token, ...]:
    return tuple(_lex_imperative(source))


def _lex_imperative(source: str) -> List[Token]:
    n = len(source)
    pos = 0
    line = 1
    col = 1
    tokens: List[Token] = []
    buf: List[str] = []
    buf_line = 1
    buf_col = 1

    def flush() -> None:
        nonlocal buf, buf_line, buf_col
        if buf:
            tokens.append(Token(TokenType.TEXT, "".join(buf), buf_line, buf_col))
            buf = []
            buf_line = line
            buf_col = col

    def advance() -> str:
        nonlocal pos, line, col
        ch = source[pos]
        pos += 1
        if ch == '\n':
            line += 1
            col = 1
        else:
            col += 1
        return ch

    def read_until(end: str) -> Tuple[str, int, int]:
        nonlocal pos, line, col
        start_pos = pos
        start_line = line
        start_col = col
        while pos < n:
            if source[pos:pos+len(end)] == end:
                result = source[start_pos:pos+len(end)]
                for _ in range(len(end)):
                    advance()
                return result, start_line, start_col
            advance()
        result = source[start_pos:]
        pos = n
        return result, start_line, start_col

    while pos < n:
        ch = source[pos]

        if ch == '{' and pos + 1 < n:
            nxt = source[pos + 1]
            if nxt == '%':
                flush()
                val, start_line, start_col = read_until('%}')
                tokens.append(Token(TokenType.BLOCK_START, val, start_line, start_col))
                continue
            elif nxt == '{':
                flush()
                val, start_line, start_col = read_until('}}')
                tokens.append(Token(TokenType.VAR_START, val, start_line, start_col))
                continue
            elif nxt == '#':
                flush()
                val, start_line, start_col = read_until('#}')
                tokens.append(Token(TokenType.COMMENT_START, val, start_line, start_col))
                continue

        buf.append(ch)
        advance()

    flush()
    tokens.append(Token(TokenType.EOF, "", line, col))
    return tokens


# ═══════════════════════════════════════════════════════════════════════
# 2. Expression tokenizer: text → tokens
# ═══════════════════════════════════════════════════════════════════════

class ExpressionTokenizer:
    @staticmethod
    def tokenize(text: str) -> Tuple[Token, ...]:
        return tuple(_expr_tokens(text))


def _expr_tokens(text: str) -> List[Token]:
    n = len(text)
    pos = 0
    line = 1
    col = 1
    tokens: List[Token] = []

    def peek(offset: int = 0) -> str:
        i = pos + offset
        return text[i] if i < n else '\0'

    def advance() -> str:
        nonlocal pos, col
        ch = text[pos]
        pos += 1
        col += 1
        return ch

    def read_string(quote: str) -> Token:
        nonlocal pos, col
        start_pos = pos
        start_col = col
        advance()  # opening quote
        while pos < n:
            ch = text[pos]
            if ch == '\\':
                advance(); advance()
                continue
            if ch == quote:
                advance()
                break
            advance()
        return Token(TokenType.STRING, text[start_pos:pos], line, start_col)

    def read_number() -> Token:
        nonlocal pos, col
        start = pos
        start_col = col
        while pos < n and (text[pos].isdigit() or text[pos] in '._'):
            advance()
        return Token(TokenType.NUMBER, text[start:pos], line, start_col)

    def read_word() -> Token:
        nonlocal pos, col
        start = pos
        start_col = col
        while pos < n and (text[pos].isalnum() or text[pos] == '_'):
            advance()
        word = text[start:pos]
        ttype = _KEYWORDS.get(word.lower(), TokenType.IDENTIFIER)
        return Token(ttype, word, line, start_col)

    MULTI_OPS = [
        ('not in', TokenType.OPERATOR), ('is not', TokenType.OPERATOR),
        ('divisible by', TokenType.OPERATOR), ('same as', TokenType.OPERATOR),
        ('starts with', TokenType.OPERATOR), ('ends with', TokenType.OPERATOR),
        ('has some', TokenType.OPERATOR), ('has every', TokenType.OPERATOR),
        ('b-and', TokenType.OPERATOR), ('b-or', TokenType.OPERATOR), ('b-xor', TokenType.OPERATOR),
    ]

    while pos < n:
        ch = text[pos]

        if ch in (' ', '\t', '\n', '\r'):
            advance()
            continue

        if ch in ('"', "'"):
            tokens.append(read_string(ch))
            continue

        if ch.isdigit() or (ch == '.' and peek(1).isdigit()):
            tokens.append(read_number())
            continue

        if ch.isalpha() or ch == '_':
            tokens.append(read_word())
            continue

        # Multi-word operators
        matched = False
        for op, ttype in MULTI_OPS:
            if text[pos:pos+len(op)] == op:
                tokens.append(Token(ttype, op, line, col))
                for _ in range(len(op)):
                    advance()
                matched = True
                break
        if matched:
            continue

        # 3-char operators
        three = text[pos:pos+3]
        if three in ('...', '<=>', '!==', '===', '?:',):
            tokens.append(Token(TokenType.OPERATOR, three, line, col))
            advance(); advance(); advance()
            continue

        # 2-char operators
        two = text[pos:pos+2]
        if two in ('..', '??', '?.', '//', '**', '==', '!=', '<=', '>=', '=>'):
            ttype = TokenType.RANGE if two == '..' else TokenType.OPERATOR
            tokens.append(Token(ttype, two, line, col))
            advance(); advance()
            continue

        # 1-char tokens
        char_map = {
            '|': TokenType.PIPE, '.': TokenType.DOT, '~': TokenType.CONCAT,
            '?': TokenType.QUESTION, ':': TokenType.COLON, ',': TokenType.COMMA,
            '(': TokenType.LPAREN, ')': TokenType.RPAREN,
            '[': TokenType.LBRACKET, ']': TokenType.RBRACKET,
            '{': TokenType.LBRACE, '}': TokenType.RBRACE,
        }
        if ch in char_map:
            tokens.append(Token(char_map[ch], ch, line, col))
        else:
            tokens.append(Token(TokenType.OPERATOR, ch, line, col))
        advance()

    tokens.append(Token(TokenType.EOF, '', line, col))
    return tokens
