"""Full-chain integration coverage for agent-CLI error delivery.

Proves that a deterministic worker failure propagates through the whole
pipeline — worker error -> pipe operator -> router -> runner ->
PipelineExecutionError -> agent_error() -> stderr — and surfaces correct
structured output in both JSON and markdown.

The LLM worker is mocked to raise a transient LLMCompletionError; every
wrapping layer below the CLI runs for real, so this catches wiring
regressions no per-worker test can (a wrapper dropping error_category, a
field agent_error() forgets to forward, a degraded error_source chain).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer
from mthds.runners.types import RunnerType

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.pipe_cmd import run_pipe_cmd
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.tools.log.log_levels import LogLevel

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

RUN_PIPE_MODULE = "pipelex.cli.agent_cli.commands.run.pipe_cmd"
ERROR_CHAIN_LIBRARY_DIR = Path("tests/integration/pipelex/cli/agent_cli")
WORKER_ERROR_MESSAGE = "LLM provider connection reset"
WORKER_MODEL = "gpt-4o-mini"
WORKER_PROVIDER = "openai"


class TestRunErrorChain:
    """`pipelex-agent run pipe` surfaces a worker failure end-to-end."""

    def _invoke_failing_run(self, mocker: MockerFixture, output_format: CliOutputFormat) -> None:
        """Run the `greet` pipe with the LLM worker mocked to fail, expecting a typer.Exit(1)."""
        # Pipelex is already booted by the module-scoped conftest fixture, so the
        # command's own boot/teardown is stubbed — only the worker call fails.
        mocker.patch(f"{RUN_PIPE_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{RUN_PIPE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{RUN_PIPE_MODULE}.resolve_pipe_from_exports", return_value=[])
        mocker.patch(f"{RUN_PIPE_MODULE}.parse_cli_inputs", return_value=None)

        transient_error = LLMCompletionError(WORKER_ERROR_MESSAGE, error_category=InferenceErrorCategory.TRANSIENT)
        # model_handle / backend_name are declared on CogtError; a real worker fills them at
        # its public-method chokepoint. This test mocks above the worker, so set them directly.
        transient_error.model_handle = WORKER_MODEL
        transient_error.backend_name = WORKER_PROVIDER
        mocker.patch.object(ContentGenerator, "make_llm_text", side_effect=transient_error)

        ctx = mocker.MagicMock()
        ctx.obj = {"log_level": LogLevel.WARNING, "runner": RunnerType.PIPELEX}

        with pytest.raises(typer.Exit) as exit_info:
            run_pipe_cmd(
                ctx=ctx,
                pipe_code="greet",
                graph=False,
                library_dir=[str(ERROR_CHAIN_LIBRARY_DIR)],
                output_format=output_format,
            )
        assert exit_info.value.exit_code == 1

    def test_run_error_chain_json(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The JSON error payload carries the worker's category, retryability, model, and source chain."""
        self._invoke_failing_run(mocker, CliOutputFormat.JSON)

        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)

        assert payload["error"] is True
        assert payload["error_type"] == "PipelineExecutionError"
        assert payload["message"]
        # error_category / retryable / model / provider originate on the worker's
        # LLMCompletionError and must survive every wrapping layer.
        assert payload["error_category"] == "transient"
        assert payload["retryable"] is True
        assert payload["error_domain"] == "runtime"
        assert payload["model"] == WORKER_MODEL
        assert payload["provider"] == WORKER_PROVIDER
        assert payload["pipe_code"] == "greet"

        # error_source is the cause chain, outermost first: runner -> router -> pipe operator -> worker.
        error_source: list[str] = payload["error_source"]
        assert isinstance(error_source, list)
        joined_source = "\n".join(error_source)
        runner_frame = joined_source.index("PipelineExecutionError")
        router_frame = joined_source.index("PipeRouterError")
        operator_frame = joined_source.index("PipeRunError")
        worker_frame = joined_source.index("LLMCompletionError")
        assert runner_frame < router_frame < operator_frame < worker_frame

    def test_run_error_chain_markdown(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The markdown error output carries the error type, message, hint, and structured details — but no source frames.

        ``error_source`` (the internal Python stack chain — ``PipeRouterError``,
        ``LLMCompletionError``, etc.) is deliberately stripped from markdown. It's
        noise for an LLM trying to fix a `.mthds` file. The JSON test above is what
        pins the wrapping-chain contract.
        """
        self._invoke_failing_run(mocker, CliOutputFormat.MARKDOWN)

        captured = capsys.readouterr()
        assert captured.out == ""
        markdown = captured.err

        assert markdown.startswith("# Error: PipelineExecutionError")
        assert WORKER_ERROR_MESSAGE in markdown
        assert "💡" in markdown  # hint callout
        assert "error_category" in markdown
        assert "transient" in markdown
        # The whole stack-trace section is gone. The stack-frame format from
        # _build_error_source is "<ExceptionType> @ <file>:<line> (in <func>)" —
        # check the section header and the frame format are both absent.
        # Note: structured cause fields like ``cause_type`` may legitimately
        # surface exception names under ``## Details``; that's not a stack frame.
        assert "## Error source" not in markdown
        assert " @ pipelex/" not in markdown
        assert "(in " not in markdown
        with pytest.raises(json.JSONDecodeError):
            json.loads(markdown)
