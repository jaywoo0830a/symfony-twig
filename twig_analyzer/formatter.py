"""Twig Formatter – reformats Twig templates with consistent style.

Handles:
- Indentation (4 spaces by default)
- Whitespace around delimiters
- Tag alignment in nested blocks
- Trimming trailing whitespace
"""

from typing import List, Tuple
import re


def format_twig(source: str, indent_size: int = 4, indent_char: str = " ") -> str:
    """Reformat a Twig template string.

    Args:
        source: Raw Twig template source
        indent_size: Number of spaces per indent level (default 4)
        indent_char: Indent character (default space)

    Returns:
        Formatted Twig source
    """
    indent_str = indent_char * indent_size
    lines = source.split("\n")
    result: List[str] = []
    indent_level = 0

    # Track block tags that increase/decrease indent
    block_start_tags = {
        "block", "for", "if", "macro", "apply", "autoescape",
        "embed", "cache", "deprecated", "sandbox", "verbatim",
        "with", "set",  # set can be block or inline
        "guard", "types",
    }
    block_mid_tags = {"else", "elseif"}
    block_end_tags = {
        "endblock", "endfor", "endif", "endmacro", "endapply",
        "endautoescape", "endembed", "endcache", "enddeprecated",
        "endsandbox", "endverbatim", "endwith", "endset",
        "endguard", "endtypes",
    }

    for raw_line in lines:
        stripped = raw_line.strip()

        # Skip empty lines
        if not stripped:
            result.append("")
            continue

        # Check if this is an end/mid tag that should decrease indent first
        tag_match = re.match(r'\{%-?\s*(\w+)', stripped)
        if tag_match:
            tag_name = tag_match.group(1)

            if tag_name in block_end_tags:
                indent_level = max(0, indent_level - 1)
            elif tag_name in block_mid_tags:
                indent_level = max(0, indent_level - 1)

        # Apply indentation
        indented = indent_str * indent_level + stripped

        # Fix whitespace around delimiters
        indented = _normalize_delimiters(indented)

        result.append(indented)

        # Check if this line starts a new block
        if tag_match:
            tag_name = tag_match.group(1)
            if tag_name in block_start_tags:
                # Don't increase indent for single-line blocks
                if not re.search(r'%\}$', stripped):
                    indent_level += 1
            elif tag_name in block_mid_tags:
                indent_level += 1

    # Join and clean up trailing whitespace
    formatted = "\n".join(result)

    # Remove multiple blank lines
    formatted = re.sub(r'\n{3,}', '\n\n', formatted)

    # Ensure single trailing newline
    formatted = formatted.rstrip("\n") + "\n"

    return formatted


def _normalize_delimiters(line: str) -> str:
    """Ensure consistent whitespace around Twig delimiters."""
    # Space after {% and before %}
    line = re.sub(r'\{%-?\s*', '{% ', line)
    line = re.sub(r'\s*-?%\}', ' %}', line)

    # Space after {{ and before }}
    line = re.sub(r'\{\{-?\s*', '{{ ', line)
    line = re.sub(r'\s*-?\}\}', ' }}', line)

    # Space after {# and before #}
    line = re.sub(r'\{\#\s*', '{# ', line)
    line = re.sub(r'\s*\#\}', ' #}', line)

    # Fix double spaces caused by normalization
    line = re.sub(r'  +', ' ', line)

    return line
