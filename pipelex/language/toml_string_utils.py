"""Shared TOML string formatting utilities.

Provides a pure function for building tomlkit string nodes with multi-line
support, used by both MthdsFactory (with config) and the agent CLI (with defaults).
"""

from __future__ import annotations

from typing import Any

from tomlkit import string as tomlkit_string


def format_toml_string(
    text: str,
    *,
    force_multiline: bool = False,
    length_limit_to_multiline: int = 100,
    ensure_trailing_newline: bool = True,
    ensure_leading_blank_line: bool = True,
    prefer_literal: bool = False,
) -> Any:  # Can't type this because of tomlkit
    r"""Build a tomlkit string node.

    - If `force_multiline` or the text contains '\n' or exceeds `length_limit_to_multiline`,
      we emit a triple-quoted multiline string.
    - When multiline, `ensure_trailing_newline` puts the closing quotes on their own line.
    - When multiline, `ensure_leading_blank_line` inserts a real blank line at the start of the string.

    Default parameter values match pipelex.toml defaults so callers without
    config access get consistent behavior.
    """
    needs_multiline = force_multiline or ("\n" in text) or len(text) > length_limit_to_multiline
    normalized = text

    if needs_multiline:
        if ensure_leading_blank_line and not normalized.startswith("\n"):
            normalized = "\n" + normalized
        if ensure_trailing_newline and not normalized.endswith("\n"):
            normalized += "\n"

    use_literal = prefer_literal and ("'''" not in normalized)
    return tomlkit_string(normalized, multiline=needs_multiline, literal=use_literal)
