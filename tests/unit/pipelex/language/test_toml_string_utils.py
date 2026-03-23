"""Unit tests for format_toml_string — shared TOML string formatting utility."""

from __future__ import annotations

import pytest

from pipelex.language.toml_string_utils import format_toml_string


class TestFormatTomlString:
    """Verify format_toml_string produces correct tomlkit string nodes."""

    def test_short_string_stays_basic(self) -> None:
        """A short string without newlines should remain a single-line basic string."""
        result = format_toml_string("hello world")
        rendered = result.as_string()
        assert rendered == '"hello world"'

    def test_newline_triggers_multiline(self) -> None:
        """A string containing newlines should become a multi-line basic string."""
        result = format_toml_string("line1\nline2")
        rendered = result.as_string()
        assert rendered.startswith('"""')
        assert "line1\nline2" in result.value

    def test_long_string_triggers_multiline(self) -> None:
        """A string exceeding length_limit_to_multiline should become multi-line."""
        long_text = "a" * 101
        result = format_toml_string(long_text)
        rendered = result.as_string()
        assert rendered.startswith('"""')

    def test_trailing_newline_added(self) -> None:
        """By default, a multi-line string gets a trailing newline."""
        result = format_toml_string("line1\nline2")
        assert result.value.endswith("\n")

    def test_leading_blank_line_added(self) -> None:
        """By default, a multi-line string gets a leading blank line."""
        result = format_toml_string("line1\nline2")
        assert result.value.startswith("\n")

    def test_no_trailing_newline_when_disabled(self) -> None:
        result = format_toml_string("line1\nline2", ensure_trailing_newline=False)
        assert result.value == "\nline1\nline2"

    def test_no_leading_blank_line_when_disabled(self) -> None:
        result = format_toml_string("line1\nline2", ensure_leading_blank_line=False)
        assert result.value == "line1\nline2\n"

    def test_force_multiline(self) -> None:
        """A short string should become multi-line when force_multiline=True."""
        result = format_toml_string("short", force_multiline=True)
        rendered = result.as_string()
        assert rendered.startswith('"""')
        assert result.value == "\nshort\n"

    def test_prefer_literal(self) -> None:
        """When prefer_literal=True, should use literal multi-line strings."""
        result = format_toml_string("line1\nline2", prefer_literal=True)
        rendered = result.as_string()
        assert rendered.startswith("'''")

    @pytest.mark.parametrize(
        "text",
        [
            "text with ''' inside",
            "'''leading triple quotes",
        ],
    )
    def test_literal_fallback_when_triple_quotes_present(self, text: str) -> None:
        """Falls back to basic multi-line when text contains triple single-quotes."""
        result = format_toml_string(text, prefer_literal=True, force_multiline=True)
        rendered = result.as_string()
        assert rendered.startswith('"""')
