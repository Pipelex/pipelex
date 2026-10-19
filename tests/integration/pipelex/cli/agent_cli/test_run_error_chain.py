"""Full-chain integration coverage for agent-CLI error delivery.

Proves that a deterministic worker failure propagates through the whole
pipeline — worker error -> pipe operator -> router -> runner ->
PipelineExecutionError -> agent_error() -> stderr — and surfaces as the
worker's problem, located at the failing pipe, in both JSON and markdown.

The LLM worker is mocked to raise a transient LLMCompletionError; every
wrapping layer below the CLI runs for real, so this catches wiring
regressions no per-worker test can (a wrapper hiding the worker's code,
a lost location, a lost model or provider, a degraded cause chain).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.pipe_cmd import run_pipe_cmd
from pipelex.cli.agent_cli.commands.run.stdin_resolver import ParsedCliInputs
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

RUN_PIPE_MODULE = "pipelex.cli.agent_cli.commands.run.pipe_cmd"
ERROR_CHAIN_LIBRARY_DIR = Path("tests/integration/pipelex/cli/agent_cli")
WORKER_ERROR_MESSAGE = "LLM provider connection reset"
WORKER_MODEL = "gpt-4o-mini"
WORKER_PROVIDER = "openai"
WORKER_ADVICE = "Wait a moment and retry"


class TestRunErrorChain:
    """`pipelex-agent run pipe` surfaces a worker failure end-to-end."""

    def _invoke_failing_run(self, mocker: MockerFixture, output_format: CliOutputFormat) -> None:
        """Run the `greet` pipe with the LLM worker mocked to fail, expecting a typer.Exit(1)."""
        # Pipelex is already booted by the module-scoped conftest fixture, so the
        # command's own boot/teardown is stubbed — only the worker call fails.
        mocker.patch(f"{RUN_PIPE_MODULE}.make_pipelex_for_agent_cli")
        mocker.patch(f"{RUN_PIPE_MODULE}.Pipelex.teardown_if_needed")
        mocker.patch(f"{RUN_PIPE_MODULE}.resolve_pipe_from_exports", return_value=[])
        mocker.patch(f"{RUN_PIPE_MODULE}.parse_cli_inputs", return_value=ParsedCliInputs(pipeline_inputs=None, inputs_base_dir=None))

        # The advice a worker's classification attaches to a transient failure, which every wrapper lets through as the hint.
        transient_error = LLMCompletionError(
            WORKER_ERROR_MESSAGE,
            error_category=InferenceErrorCategory.TRANSIENT,
            user_action=UserAction(kind=UserActionKind.WAIT_AND_RETRY, detail=WORKER_ADVICE),
        )
        # model_handle / backend_name are declared on CogtError; a real worker fills them at
        # its public-method chokepoint. This test mocks above the worker, so set them directly.
        transient_error.model_handle = WORKER_MODEL
        transient_error.backend_name = WORKER_PROVIDER
        mocker.patch.object(ContentGenerator, "make_llm_text", side_effect=transient_error)

        with pytest.raises(typer.Exit) as exit_info:
            run_pipe_cmd(
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
        """The JSON problem is the worker's: its code and retry verdict, located at the pipe, with the model, provider and chain."""
        self._invoke_failing_run(mocker, CliOutputFormat.JSON)

        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)

        # The code, the domain and the verdict originate on the worker's LLMCompletionError and survive every wrapping layer.
        assert payload["code"] == "provider.unavailable"
        assert payload["domain"] == "runtime"
        assert payload["retry"] == "yes"
        assert payload["location"] == {"pipe": "greet", "path": ["greet"]}
        assert payload["message"] == f"Pipe 'greet' failed: {WORKER_ERROR_MESSAGE}"
        diagnostics = payload["diagnostics"]
        assert diagnostics["error_class"] == "LLMCompletionError"
        assert diagnostics["model"] == WORKER_MODEL
        assert diagnostics["provider"]["name"] == WORKER_PROVIDER
        for retired in ("error", "error_type", "error_category", "retryable", "hint", "error_source", "cause_type", "pipe_stack"):
            assert retired not in payload

    def test_run_error_chain_markdown(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The markdown problem names the fault, the next step, the worker's advice, the place, the model and provider — no source frames."""
        self._invoke_failing_run(mocker, CliOutputFormat.MARKDOWN)

        captured = capsys.readouterr()
        assert captured.out == ""
        markdown = captured.err

        assert markdown.startswith("## ")
        assert WORKER_ERROR_MESSAGE in markdown
        assert "**Next step** (`retry`)" in markdown
        assert f"💡 {WORKER_ADVICE}" in markdown
        assert "- Code: `provider.unavailable` (domain runtime, retry yes)" in markdown
        assert "- Location: pipe 'greet', path greet" in markdown
        assert f"- Model: `{WORKER_MODEL}`" in markdown
        assert f"- Provider: `{WORKER_PROVIDER}`" in markdown
        # No stack frame reaches the agent: the frame format "<ExceptionType> @ <file>:<line> (in <func>)" is absent.
        assert " @ pipelex/" not in markdown
        assert "(in " not in markdown
        with pytest.raises(json.JSONDecodeError):
            json.loads(markdown)
