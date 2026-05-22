"""Twig Formatter – functional, pure-transformation pipeline.

Core ideas:
- Immutable: input → transform → output, no mutation
- Composable: small pure functions chained via fold
- Declarative: describe WHAT, not HOW
- HTML-aware: understands both Twig blocks and HTML element nesting
"""

from __future__ import annotations
from typing import FrozenSet, List, NamedTuple, Optional, Tuple
import re
from functools import reduce


# ═══════════════════════════════════════════════════════════════════════
# 1. Types — immutable data containers
# ═══════════════════════════════════════════════════════════════════════

class Line(NamedTuple):
    raw: str
    stripped: str

    @staticmethod
    def of(text: str) -> "Line":
        return Line(raw=text, stripped=text.strip())

    @property
    def is_empty(self) -> bool:
        return self.stripped == ""


class TagMatch(NamedTuple):
    name: str
    is_block_start: bool
    is_block_mid: bool
    is_block_end: bool

    @staticmethod
    def from_line(ln: Line) -> Optional["TagMatch"]:
        m = re.match(r'\{[%#]-?\s*(\w+)', ln.stripped)
        if m is None:
            return None
        name = m.group(1)
        return TagMatch(
            name=name,
            is_block_start=name in BLOCK_START_TAGS,
            is_block_mid=name in BLOCK_MID_TAGS,
            is_block_end=name in BLOCK_END_TAGS,
        )


class HtmlMatch(NamedTuple):
    opens: int   # opening tags <x>
    closes: int  # closing </x> or self-closing <x/>

    @staticmethod
    def from_line(ln: Line) -> "HtmlMatch":
        cleaned = _remove_twig(ln.stripped)
        # Opening tags: <tag ...> (not </tag>, not <tag/>)
        opens = len(re.findall(r'<(?!\/)([\w][\w-]*)\b[^>]*?(?<![\/])>', cleaned))
        # Closing + self-closing: </tag>, <tag/>
        closes = len(re.findall(r'<\/([\w][\w-]*)>|<\w[\w-]*[^>]*?\/>', cleaned))
        return HtmlMatch(opens=opens, closes=closes)


# ═══════════════════════════════════════════════════════════════════════
# 2. Configuration — immutable sets
# ═══════════════════════════════════════════════════════════════════════

BLOCK_START_TAGS: FrozenSet[str] = frozenset({
    "block", "for", "if", "macro", "apply", "autoescape",
    "embed", "cache", "deprecated", "sandbox", "verbatim",
    "with", "guard",
})

BLOCK_MID_TAGS: FrozenSet[str] = frozenset({"else", "elseif"})

BLOCK_END_TAGS: FrozenSet[str] = frozenset({
    "endblock", "endfor", "endif", "endmacro", "endapply",
    "endautoescape", "endembed", "endcache", "enddeprecated",
    "endsandbox", "endverbatim", "endwith", "endset",
    "endguard", "endtypes",
})

INLINE_BLOCK_TAGS: FrozenSet[str] = frozenset({"set", "types"})


# ═══════════════════════════════════════════════════════════════════════
# 3. Pure transformations
# ═══════════════════════════════════════════════════════════════════════

def _remove_twig(text: str) -> str:
    """Remove all Twig syntax from text, leaving only HTML."""
    text = re.sub(r'\{\{[^}]*?\}\}', '', text)   # {{ ... }}
    text = re.sub(r'\{%[^}]*?%\}', '', text)     # {% ... %}
    text = re.sub(r'\{\#[^}]*?\#\}', '', text)   # {# ... #}
    return text


def _normalize_delimiters(line: str) -> str:
    """One space inside Twig delimiters."""
    line = re.sub(r'\{%-?\s*', '{% ', line)
    line = re.sub(r'\s*-?%\}', ' %}', line)
    line = re.sub(r'\{\{-?\s*', '{{ ', line)
    line = re.sub(r'\s*-?\}\}', ' }}', line)
    line = re.sub(r'\{\#-?\s*', '{# ', line)
    line = re.sub(r'\s*-?\#\}', ' #}', line)
    return line


def _trim_trailing(line: str) -> str:
    return line.rstrip()


def _is_single_line_block(ln: Line) -> bool:
    """A block-start tag is single-line if it closes on the same line.

    Examples:
      {% block title %}text{% endblock %} → True (has endblock on same line)
      {% set x = 1 %}                     → True (inline, has content before %})
      {% if x %}a{% endif %}              → True (has endif on same line)
      {% block content %}                 → False (opens a multi-line block)
      {% for item in items %}             → False (opens a multi-line block)
    """
    tag = TagMatch.from_line(ln)
    if tag is None:
        return False

    # Case 1: Same-line matching end tag (e.g., {% block X %}...{% endblock %})
    if re.search(r'\{%-?\s*end' + re.escape(tag.name) + r'\b', ln.stripped):
        return True

    # Case 2: Inline tag with content before %} (e.g., {% set x = 1 %})
    # Only applies to certain tags that can be both block and inline
    if tag.name in INLINE_BLOCK_TAGS:
        # Check if there's actual content after the tag name before %}
        m = re.match(r'\{%-?\s*' + re.escape(tag.name) + r'\s+(.+?)%\}', ln.stripped)
        if m is not None:
            return True

    return False


# ═══════════════════════════════════════════════════════════════════════
# 4. State — accumulator for the fold (immutable)
# ═══════════════════════════════════════════════════════════════════════

class FormatState(NamedTuple):
    level: int
    prev_empty: bool
    lines: List[str]

    @staticmethod
    def empty() -> "FormatState":
        return FormatState(level=0, prev_empty=False, lines=[])


# ═══════════════════════════════════════════════════════════════════════
# 5. Core reducer — pure Line × State → State
# ═══════════════════════════════════════════════════════════════════════

def _compute_indent_change(ln: Line) -> Tuple[int, int]:
    """(pre_change, post_change) for a line."""
    pre = 0
    post = 0

    tag = TagMatch.from_line(ln)
    html = HtmlMatch.from_line(ln)

    # Twig: block-end decreases BEFORE rendering, block-start increases AFTER
    if tag is not None:
        if tag.is_block_end:
            pre -= 1
        elif tag.is_block_mid:
            pre -= 1
            post += 1
        elif tag.is_block_start and not _is_single_line_block(ln):
            post += 1

    # HTML: net close decreases BEFORE, net open increases AFTER
    net = html.opens - html.closes
    if net < 0:
        pre += net
    elif net > 0:
        post += net

    return pre, post


def _process_line(state: FormatState, ln: Line) -> FormatState:
    """Fold: FormatState → Line → FormatState"""
    if ln.is_empty:
        if state.prev_empty:
            return state
        return FormatState(level=state.level, prev_empty=True, lines=state.lines + [""])

    pre_change, post_change = _compute_indent_change(ln)
    current = max(0, state.level + pre_change)

    indent = " " * (current * 4)
    content = _trim_trailing(_normalize_delimiters(ln.stripped))

    nxt = max(0, current + post_change)
    return FormatState(level=nxt, prev_empty=False, lines=state.lines + [indent + content])


# ═══════════════════════════════════════════════════════════════════════
# 6. Post-processing (pure)
# ═══════════════════════════════════════════════════════════════════════

def _post_process(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    if not text.endswith('\n'):
        text += '\n'
    return '\n'.join(line.rstrip() for line in text.split('\n'))


# ═══════════════════════════════════════════════════════════════════════
# 7. Public API
# ═══════════════════════════════════════════════════════════════════════

def format_twig(source: str, indent_size: int = 4) -> str:
    """Reformat a Twig template. Pure: source → formatted."""
    # Adjust indent if needed (default 4 spaces = 1 char per level in our indent calc)
    lines = [Line.of(ln) for ln in source.split('\n')]
    final = reduce(_process_line, lines, FormatState.empty())
    result = '\n'.join(final.lines)
    return _post_process(result)
