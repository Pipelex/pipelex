"""Tests for is_traceback_requested().

Verifies that the function correctly reads the --traceback flag from the Click context.
"""

from __future__ import annotations

import click

from pipelex.cli.error_handlers import is_traceback_requested


class TestIsTracebackRequested:
    """Unit tests for is_traceback_requested()."""

    def test_returns_false_when_no_click_context(self) -> None:
        """Outside a Click context, should return False."""
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
