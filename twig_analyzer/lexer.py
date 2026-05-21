"""Twig Lexer – state-machine tokenizer for Twig templates.

Clean two-level approach:
1. Lexer: splits source into TEXT, BLOCK_START/END, VAR_START/END, COMMENT_START/END
2. ExpressionTokenizer: tokenizes content inside {{ }} or {% %} expressions
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import List
import re


class TokenType(Enum):
    TEXT = auto()
    BLOCK_START = auto()
    BLOCK_END = auto()
    VAR_START = auto()
    VAR_END = auto()
    COMMENT_START = auto()
    COMMENT_END = auto()

    IDENTIFIER = auto()
    STRING = auto()
    NUMBER = auto()
    BOOLEAN = auto()
    NULL = auto()

    OPERATOR = auto()
    DOT = auto()
    NULL_SAFE_DOT = auto()
    PIPE = auto()
    ARROW = auto()
    ASSIGN = auto()
    SPREAD = auto()
    RANGE = auto()
    CONCAT = auto()
    QUESTION = auto()
    COLON = auto()
    COMMA = auto()

    LPAREN = auto()
    RPAREN = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LBRACE = auto()
    RBRACE = auto()

    EOF = auto()


KEYWORDS = {
    "true": TokenType.BOOLEAN, "false": TokenType.BOOLEAN,
    "null": TokenType.NULL, "none": TokenType.NULL,
}


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    column: int
    end_line: int = 0
    end_column: int = 0

    def __post_init__(self):
        if self.end_line == 0:
            self.end_line = self.line
            self.end_column = self.column + (len(self.value) if self.value else 0)


class Lexer:
    """State-machine lexer: scans character by character for Twig delimiters."""

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1
        self.tokens: List[Token] = []

    def tokenize(self) -> List[Token]:
        self.tokens = []
        self.pos = 0
        self.line = 1
        self.col = 1
        text_buf: List[str] = []
        text_line = 1
        text_col = 1

        def flush_text():
            nonlocal text_buf, text_line, text_col
            if text_buf:
                val = "".join(text_buf)
                self.tokens.append(Token(TokenType.TEXT, val, text_line, text_col))
                text_buf = []
                text_line = self.line
                text_col = self.col

        n = len(self.source)
        while self.pos < n:
            ch = self.source[self.pos]

            if ch == "{":
                # Look ahead to determine delimiter type
                if self.pos + 1 < n:
                    nxt = self.source[self.pos + 1]
                    if nxt in ("%", "{", "#"):
                        flush_text()
                        if nxt == "%":
                            self._emit_delim(TokenType.BLOCK_START)
                        elif nxt == "{":
                            self._emit_delim(TokenType.VAR_START)
                        elif nxt == "#":
                            self._emit_delim(TokenType.COMMENT_START)
                        continue
                text_buf.append(ch)
                self._adv()
            elif ch in ("%", "}", "#") and self.pos + 1 < n and self.source[self.pos + 1] == "}":
                # Check if this is a closing delimiter preceded by whitespace control
                flush_text()
                if ch == "%":
                    self._emit_delim(TokenType.BLOCK_END)
                elif ch == "}":
                    self._emit_delim(TokenType.VAR_END)
                elif ch == "#":
                    self._emit_delim(TokenType.COMMENT_END)
                continue
            else:
                text_buf.append(ch)
                self._adv()

        flush_text()
        self.tokens.append(Token(TokenType.EOF, "", self.line, self.col))
        return self.tokens

    def _emit_delim(self, ttype: TokenType) -> None:
        """Emit a delimiter token: reads `{%, }}`, etc. including whitespace modifiers."""
        start_line = self.line
        start_col = self.col
        # Read the opening `{` or closing char
        buf = [self.source[self.pos]]
        self._adv()
        if self.pos < len(self.source):
            buf.append(self.source[self.pos])
            self._adv()
        # Read optional whitespace control modifiers after {%
        if ttype in (TokenType.BLOCK_START, TokenType.VAR_START):
            while self.pos < len(self.source) and self.source[self.pos] in ("-", "~", " ", "\t"):
                buf.append(self.source[self.pos])
                self._adv()
        # Read optional whitespace control modifiers before %}
        if ttype in (TokenType.BLOCK_END, TokenType.VAR_END):
            while self.pos < len(self.source) and self.source[self.pos] in ("-", "~", " ", "\t"):
                buf.append(self.source[self.pos])
                self._adv()
        value = "".join(buf)
        self.tokens.append(Token(ttype, value, start_line, start_col))

    def _adv(self) -> None:
        if self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1
            self.pos += 1


# ============================================================
# Expression Tokenizer
# ============================================================

# Token patterns in precedence order (longer matches first)
_EXPR_PATTERNS = [
    # Strings (with escape handling)
    (r'"(?:[^"\\]|\\.)*"', TokenType.STRING),
    (r"'(?:[^'\\]|\\.)*'", TokenType.STRING),
    # Multi-char operators
    (r'\.\.\.', TokenType.SPREAD),
    (r'\.\.', TokenType.RANGE),
    (r'\?\.', TokenType.NULL_SAFE_DOT),
    (r'<=>', TokenType.OPERATOR),
    (r'[!=]==?', TokenType.OPERATOR),
    (r'[<>]=?', TokenType.OPERATOR),
    (r'=>', TokenType.ARROW),
    (r'\*\*', TokenType.OPERATOR),
    (r'//', TokenType.OPERATOR),
    (r'b-(?:and|xor|or)', TokenType.OPERATOR),
    # Numbers (allow underscores)
    (r'\d[_\d]*(?:\.\d[_\d]*)?', TokenType.NUMBER),
    # Identifiers
    (r'[a-zA-Z_\x7f-\xff][a-zA-Z0-9_\x7f-\xff]*', TokenType.IDENTIFIER),
    # Single-char tokens
    (r'\.', TokenType.DOT),
    (r'\|', TokenType.PIPE),
    (r'~', TokenType.CONCAT),
    (r'\?', TokenType.QUESTION),
    (r':', TokenType.COLON),
    (r',', TokenType.COMMA),
    (r'\(', TokenType.LPAREN),
    (r'\)', TokenType.RPAREN),
    (r'\[', TokenType.LBRACKET),
    (r'\]', TokenType.RBRACKET),
    (r'\{', TokenType.LBRACE),
    (r'\}', TokenType.RBRACE),
    (r'=', TokenType.ASSIGN),
    (r'[+\-*/%]', TokenType.OPERATOR),
    # Skip: whitespace and inline comments
    (r'[ \t\r\n]+', None),
    (r'#[^\n]*', None),
]

_EXPR_RE = re.compile('|'.join(
    f'(?P<G{i}>{p})' for i, (p, _) in enumerate(_EXPR_PATTERNS)
))


class ExpressionTokenizer:
    """Tokenizes content inside {{ }} or {% %} tags."""

    def __init__(self, source: str, start_line: int = 1, start_col: int = 1):
        self.source = source
        self.line = start_line
        self.col = start_col

    def tokenize(self) -> List[Token]:
        tokens: List[Token] = []
        for m in _EXPR_RE.finditer(self.source):
            grp = m.lastgroup
            if grp is None:
                continue
            idx = int(grp[1:])
            ttype = _EXPR_PATTERNS[idx][1]
            value = m.group()
            self._adv(value)
            if ttype is None:
                continue
            if ttype == TokenType.IDENTIFIER and value in KEYWORDS:
                ttype = KEYWORDS[value]
            tokens.append(Token(ttype, value, self.line, self.col))
        tokens.append(Token(TokenType.EOF, "", self.line, self.col))
        return tokens

    def _adv(self, text: str) -> None:
        for ch in text:
            if ch == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1
