"""Unit tests for agent CLI `run method` resolving a relative --inputs path against the method dir."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import pytest
from mthds.runners.types import RunnerType

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

RUN_METHOD_MODULE = "pipelex.cli.agent_cli.commands.run.method_cmd"


class TestAgentRunMethodInputsResolution:
    @pytest.fixture
    def tty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Make stdin look like a TTY so parse_cli_inputs skips the stdin fallback."""
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

    def _patch_method_run(self, mocker: MockerFixture, *, method_dir: Path, result: dict[str, Any]) -> Any:
        """Patch method resolution + runner dependencies; return the run_pipeline_core mock."""
        method_mock = mocker.MagicMock()
        method_mock.mthds_files = []
        method_mock.path = method_dir
        mocker.patch(
            f"{RUN_METHOD_MODULE}.resolve_method_target",
            return_value=("my_pipe", [str(method_dir)], method_mock),
        )
        mocker.patch(f"{RUN_METHOD_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{RUN_METHOD_MODULE}.Pipelex.teardown_if_needed")
        return mocker.patch(f"{RUN_METHOD_MODULE}.run_pipeline_core", new=mocker.AsyncMock(return_value=result))

    def _make_ctx(self, mocker: MockerFixture) -> Any:
        ctx = mocker.MagicMock()
        ctx.obj = {"runner": RunnerType.PIPELEX}
        return ctx

    @pytest.mark.usefixtures("tty_stdin")
    def test_relative_inputs_resolved_against_method_dir(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """A relative --inputs path loads from the method's directory, not the CWD (same rule as the main CLI)."""
        (tmp_path / "inputs.toml").write_text('topic = "cats"\n', encoding="utf-8")
        run_core_mock = self._patch_method_run(mocker, method_dir=tmp_path, result={"answer": "42"})

        run_method_cmd(ctx=self._make_ctx(mocker), name="my-method", inputs="inputs.toml", output_format=CliOutputFormat.JSON)

        capsys.readouterr()
        assert run_core_mock.call_args.kwargs["inputs"] == {"topic": "cats"}

    @pytest.mark.usefixtures("tty_stdin")
    def test_inline_json_untouched_by_resolution(self, mocker: MockerFixture, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Inline JSON --inputs is parsed as-is, never treated as a path."""
        run_core_mock = self._patch_method_run(mocker, method_dir=tmp_path, result={"answer": "42"})

        run_method_cmd(ctx=self._make_ctx(mocker), name="my-method", inputs='{"topic": "inline"}', output_format=CliOutputFormat.JSON)

        capsys.readouterr()
        assert run_core_mock.call_args.kwargs["inputs"] == {"topic": "inline"}
