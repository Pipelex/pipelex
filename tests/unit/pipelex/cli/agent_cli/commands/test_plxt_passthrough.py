"""Unit tests for plxt passthrough, fmt_cmd, and lint_cmd."""

from __future__ import annotations

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.agent_cli.commands.fmt_cmd import fmt_cmd
from pipelex.cli.agent_cli.commands.lint_cmd import lint_cmd
from pipelex.cli.agent_cli.commands.plxt_passthrough import run_plxt
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsEnvVar

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestPlxtPassthrough:
    """Tests for run_plxt(), fmt_cmd(), and lint_cmd() delegation to the plxt binary."""

    def test_run_plxt_reports_the_missing_tool_when_plxt_missing(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """run_plxt exits with code 1 and the client.tool_missing problem naming plxt when plxt is not on PATH."""
        mocker.patch("shutil.which", return_value=None)

        with pytest.raises(typer.Exit) as exc_info:
            run_plxt("fmt", file_path="file.mthds")

        assert exc_info.value.exit_code == 1
        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == "client.tool_missing"
        assert parsed["params"] == {"tool": "plxt"}

    def test_error_message_references_uv_tool_install(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Error message tells the user how to install pipelex-tools."""
        mocker.patch("shutil.which", return_value=None)

        with pytest.raises(typer.Exit):
            run_plxt("lint", file_path="file.mthds")

        parsed = json.loads(capsys.readouterr().err)
        assert "uv tool install pipelex-tools" in parsed["message"]

    @pytest.mark.parametrize(
        ("topic", "exit_code"),
        [
            ("success", 0),
            ("general failure", 1),
            ("custom exit code", 42),
        ],
    )
    def test_run_plxt_propagates_exit_code(
        self,
        mocker: MockerFixture,
        topic: str,  # ruff: ignore[unused-method-argument]
        exit_code: int,
    ) -> None:
        """run_plxt propagates the subprocess exit code via typer.Exit."""
        mocker.patch("shutil.which", return_value="/usr/bin/plxt")
        mocker.patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=exit_code),
        )

        with pytest.raises(typer.Exit) as exc_info:
            run_plxt("fmt", file_path="file.mthds")

        assert exc_info.value.exit_code == exit_code

    def test_subprocess_args_passed_correctly(
        self,
        mocker: MockerFixture,
    ) -> None:
        """run_plxt passes [plxt_path, subcommand, file_path] to subprocess.run, with plxt's own usage statistics off.

        The child's environment is compared by the one variable it adds, never printed whole: it holds the caller's.
        """
        mocker.patch("shutil.which", return_value="/usr/bin/plxt")
        mock_run = mocker.patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(args=[], returncode=0),
        )

        with pytest.raises(typer.Exit):
            run_plxt("fmt", file_path="/path/to/file.mthds")

        assert mock_run.call_count == 1
        call_args, call_kwargs = mock_run.call_args
        assert call_args == (["/usr/bin/plxt", "fmt", "/path/to/file.mthds"],)
        assert sorted(call_kwargs) == ["check", "env"]
        assert call_kwargs["check"] is False
        assert call_kwargs["env"].get(UsageStatsEnvVar.TOOL_SWITCH) == "0"

    def test_fmt_cmd_delegates_to_plxt_with_fmt_subcommand(
        self,
        mocker: MockerFixture,
    ) -> None:
        """fmt_cmd calls run_plxt with 'fmt' subcommand."""
        mock_run_plxt = mocker.patch(
            "pipelex.cli.agent_cli.commands.fmt_cmd.run_plxt",
        )

        fmt_cmd("some/file.mthds")

        mock_run_plxt.assert_called_once_with("fmt", file_path="some/file.mthds")

    def test_lint_cmd_delegates_to_plxt_with_lint_subcommand(
        self,
        mocker: MockerFixture,
    ) -> None:
        """lint_cmd calls run_plxt with 'lint' subcommand."""
        mock_run_plxt = mocker.patch(
            "pipelex.cli.agent_cli.commands.lint_cmd.run_plxt",
        )

        lint_cmd("some/file.mthds")

        mock_run_plxt.assert_called_once_with("lint", file_path="some/file.mthds")
