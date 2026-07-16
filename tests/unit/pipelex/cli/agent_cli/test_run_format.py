"""Unit tests for the agent CLI run command --format option."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from mthds.runners.types import RunnerType

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.pipe_cmd import run_pipe_cmd
from pipelex.cli.agent_cli.commands.run.stdin_resolver import ParsedCliInputs

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

RUN_PIPE_MODULE = "pipelex.cli.agent_cli.commands.run.pipe_cmd"


class TestRunFormat:
    """run pipe emits markdown by default and JSON with --format json."""

    def _patch_run(self, mocker: MockerFixture, result: dict[str, Any]) -> Any:
        """Patch the run pipe command's dependencies and return a mock typer context."""
        mocker.patch(f"{RUN_PIPE_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{RUN_PIPE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{RUN_PIPE_MODULE}.resolve_pipe_from_exports", return_value=[])
        mocker.patch(f"{RUN_PIPE_MODULE}.parse_cli_inputs", return_value=ParsedCliInputs(pipeline_inputs=None, inputs_base_dir=None))
        mocker.patch(f"{RUN_PIPE_MODULE}.run_pipeline_core", new=mocker.AsyncMock(return_value=result))
        ctx = mocker.MagicMock()
        ctx.obj = {"runner": RunnerType.PIPELEX}
        return ctx

    def test_run_pipe_markdown_is_default(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Run pipe with no --format produces markdown to stdout."""
        ctx = self._patch_run(mocker, {"answer": "42"})

        run_pipe_cmd(ctx=ctx, pipe_code="my_pipe", output_format=CliOutputFormat.MARKDOWN)

        out = capsys.readouterr().out
        assert out.startswith("# Pipeline run complete")
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)

    def test_run_pipe_json_with_format_json(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Run pipe --format json produces valid JSON to stdout."""
        ctx = self._patch_run(mocker, {"answer": "42"})

        run_pipe_cmd(ctx=ctx, pipe_code="my_pipe", output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed == {"answer": "42"}
