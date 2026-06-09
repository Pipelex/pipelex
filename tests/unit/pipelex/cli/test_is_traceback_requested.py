"""Tests for is_traceback_requested().

Verifies that the function honors the parse-time flag (set via set_traceback_requested)
and, as a fallback, the --traceback flag carried on an explicitly-pushed Click context.
"""

from __future__ import annotations

import click

from pipelex.cli.error_handlers import is_traceback_requested, set_traceback_requested


class TestIsTracebackRequested:
    """Unit tests for is_traceback_requested()."""

    def test_returns_true_from_parse_time_flag_without_click_context(self) -> None:
        """Regression: the flag recorded at parse time is honored with NO active Click
        context. typer >= 0.26 / click >= 8.4 do not push a global context during
        subcommand dispatch, which silently disabled --traceback when the flag was read
        through click.get_current_context().
        """
        set_traceback_requested(True)
        assert is_traceback_requested() is True

    def test_returns_false_when_no_click_context(self) -> None:
        """Outside a Click context and with no parse-time flag, should return False."""
        assert is_traceback_requested() is False

    def test_returns_false_when_flag_not_set(self) -> None:
        """When ctx.obj has no 'traceback' key, should return False."""
        ctx = click.Context(click.Command("test"), obj={})
        with ctx:
            assert is_traceback_requested() is False

    def test_returns_true_when_flag_set(self) -> None:
        """When ctx.obj['traceback'] is True, should return True."""
        ctx = click.Context(click.Command("test"), obj={"traceback": True})
        with ctx:
            assert is_traceback_requested() is True

    def test_returns_false_when_flag_explicitly_false(self) -> None:
        """When ctx.obj['traceback'] is False, should return False."""
        ctx = click.Context(click.Command("test"), obj={"traceback": False})
        with ctx:
            assert is_traceback_requested() is False
