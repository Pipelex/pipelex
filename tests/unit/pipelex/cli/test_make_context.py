"""Tests for PipelexCLI.make_context intercepting --traceback.

Verifies that the custom CLI group correctly strips --traceback from args
and stores it in ctx.obj.
"""

from __future__ import annotations

import click

from pipelex.cli._cli import PipelexCLI


class TestPipelexCLIMakeContext:
    """Test that PipelexCLI.make_context intercepts --traceback."""

    def test_traceback_flag_intercepted(self) -> None:
        """--traceback should be removed from args and stored in ctx.obj."""
        group = PipelexCLI(name="pipelex")
        group.add_command(click.Command("dummy"))

        ctx = group.make_context("pipelex", ["--traceback", "dummy"])
        assert ctx.obj["traceback"] is True

    def test_no_traceback_flag(self) -> None:
        """Without --traceback, ctx.obj['traceback'] should be False."""
        group = PipelexCLI(name="pipelex")
        group.add_command(click.Command("dummy"))

        ctx = group.make_context("pipelex", ["dummy"])
        assert ctx.obj["traceback"] is False
