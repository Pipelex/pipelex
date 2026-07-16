from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from mthds.runners.types import RunnerType

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.pipe_cmd import run_pipe_cmd
from pipelex.cli.agent_cli.commands.run.stdin_resolver import ParsedCliInputs

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

RUN_PIPE_MODULE = "pipelex.cli.agent_cli.commands.run.pipe_cmd"


class TestErrorFormatIndependent:
    def _patch_success(self, mocker: MockerFixture, result: dict[str, Any]) -> Any:
        """Patch the run pipe command's dependencies for the success path."""
        mocker.patch(f"{RUN_PIPE_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{RUN_PIPE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{RUN_PIPE_MODULE}.resolve_pipe_from_exports", return_value=[])
        mocker.patch(f"{RUN_PIPE_MODULE}.parse_cli_inputs", return_value=ParsedCliInputs(pipeline_inputs=None, inputs_base_dir=None))
        mocker.patch(f"{RUN_PIPE_MODULE}.run_pipeline_core", new=mocker.AsyncMock(return_value=result))
        ctx = mocker.MagicMock()
        ctx.obj = {"runner": RunnerType.PIPELEX}
        return ctx

    def _ctx_for_error_path(self, mocker: MockerFixture) -> Any:
        """Mock typer.Context shaped for the error path (no Pipelex init needed)."""
        ctx = mocker.MagicMock()
        ctx.obj = {"runner": RunnerType.PIPELEX}
        return ctx

    @pytest.mark.parametrize(
        ("output_format", "error_format", "expected_success_is_markdown"),
        [
            # Cell 1: inherit, markdown — default behavior
            (CliOutputFormat.MARKDOWN, None, True),
            # Cell 2: inherit, json — regression guard for today's `--format json` flipping both
            (CliOutputFormat.JSON, None, False),
            # Cell 3: error-only override — markdown success, json error
            (CliOutputFormat.MARKDOWN, CliOutputFormat.JSON, True),
            # Cell 4: cross-flip — json success, markdown error
            (CliOutputFormat.JSON, CliOutputFormat.MARKDOWN, False),
        ],
    )
    def test_success_path_follows_output_format(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        output_format: CliOutputFormat,
        error_format: CliOutputFormat | None,
        expected_success_is_markdown: bool,
    ) -> None:
        """Success output follows --format regardless of --error-format."""
        ctx = self._patch_success(mocker, {"answer": "42"})

        run_pipe_cmd(ctx=ctx, pipe_code="my_pipe", output_format=output_format, error_format=error_format)

        out = capsys.readouterr().out
        if expected_success_is_markdown:
            assert out.startswith("# Pipeline run complete")
            with pytest.raises(json.JSONDecodeError):
                json.loads(out)
        else:
            assert json.loads(out) == {"answer": "42"}

    @pytest.mark.parametrize(
        ("output_format", "error_format", "expected_error_is_markdown"),
        [
            # Cell 1: inherit, markdown
            (CliOutputFormat.MARKDOWN, None, True),
            # Cell 2: inherit, json
            (CliOutputFormat.JSON, None, False),
            # Cell 3: error-only override — markdown success, json error
            (CliOutputFormat.MARKDOWN, CliOutputFormat.JSON, False),
            # Cell 4: cross-flip — json success, markdown error
            (CliOutputFormat.JSON, CliOutputFormat.MARKDOWN, True),
        ],
    )
    def test_error_path_follows_error_format(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        output_format: CliOutputFormat,
        error_format: CliOutputFormat | None,
        expected_error_is_markdown: bool,
    ) -> None:
        """Error output follows --error-format (or --format when --error-format is omitted)."""
        ctx = self._ctx_for_error_path(mocker)

        # Passing a pipe_code that ends in .mthds triggers the ArgumentError branch in run_pipe_cmd.
        with pytest.raises(typer.Exit):
            run_pipe_cmd(ctx=ctx, pipe_code="my_pipe.mthds", output_format=output_format, error_format=error_format)

        err = capsys.readouterr().err
        if expected_error_is_markdown:
            assert err.startswith("# Error: ArgumentError")
            with pytest.raises(json.JSONDecodeError):
                json.loads(err)
        else:
            parsed = json.loads(err)
            assert parsed["error"] is True
            assert parsed["error_type"] == "ArgumentError"
