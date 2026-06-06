"""Unit tests for the ``--mock-inference`` CLI surface on the run subcommands.

Two cheap, no-boot checks: every run subcommand declares the option, and each rejects combining
``--mock-inference`` with ``--dry-run`` (the two are mutually exclusive — dry-run swaps the generator
pre-dispatch, so the leaf mock would be silently ignored). The guard runs at the top of each command,
before any filesystem access or Pipelex boot, so calling the command function directly is enough.
"""

from collections.abc import Callable
from inspect import signature

import pytest
import typer

from pipelex.cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.commands.run.pipe_cmd import run_pipe_cmd


class TestMockInferenceCliGuard:
    @pytest.mark.parametrize("command", [run_pipe_cmd, run_bundle_cmd, run_method_cmd])
    def test_run_command_declares_mock_inference(self, command: Callable[..., None]) -> None:
        assert "mock_inference" in signature(command).parameters, f"{command.__name__} must declare a --mock-inference option"

    @pytest.mark.parametrize(
        "command, required_kwargs",
        [
            (run_pipe_cmd, {"pipe_code": "some_pipe"}),
            (run_bundle_cmd, {"path": "some_path"}),
            (run_method_cmd, {"name": "some_method"}),
        ],
    )
    def test_rejects_mock_inference_combined_with_dry_run(self, command: Callable[..., None], required_kwargs: dict[str, str]) -> None:
        with pytest.raises(typer.Exit):
            command(dry_run=True, mock_inference=True, **required_kwargs)
