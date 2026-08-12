"""Unit tests for the hidden ``--mock-usage`` CLI surface on the run subcommands.

Two cheap, no-boot checks: every run subcommand declares the option (hidden — for the
distributed-execution validation scripts, not for ``--help``), and each rejects ``--mock-usage``
without ``--dry-run`` (it is a sub-flag of the dry run). The guard runs at the top of each command,
before any filesystem access or Pipelex boot, so calling the command function directly is enough.
"""

from collections.abc import Callable
from inspect import signature

import pytest
import typer

from pipelex.cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.commands.run.pipe_cmd import run_pipe_cmd


class TestMockUsageCliGuard:
    @pytest.mark.parametrize("command", [run_pipe_cmd, run_bundle_cmd, run_method_cmd])
    def test_run_command_declares_mock_usage(self, command: Callable[..., None]) -> None:
        assert "mock_usage" in signature(command).parameters, f"{command.__name__} must declare a --mock-usage option"

    @pytest.mark.parametrize(
        ("command", "required_kwargs"),
        [
            (run_pipe_cmd, {"pipe_code": "some_pipe"}),
            (run_bundle_cmd, {"path": "some_path"}),
            (run_method_cmd, {"name": "some_method"}),
        ],
    )
    def test_rejects_mock_usage_without_dry_run(self, command: Callable[..., None], required_kwargs: dict[str, str]) -> None:
        with pytest.raises(typer.Exit):
            command(dry_run=False, mock_usage=True, **required_kwargs)
