"""Unit tests: `pipelex-agent run … --runner hosted` answers in the run envelope a local run answers in.

`run_hosted` is mocked at the agent CLI seam, so no request leaves.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from pipelex_sdk.error_models import RunErrorReport
from pipelex_sdk.errors import RunFailedError
from pipelex_sdk.runs import RunResults, RunStatus
from pipelex_sdk.upload import UploadRecord

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.hosted_run import HostedRunOutcome
from pipelex.hosted.run_config import RunExecution

if TYPE_CHECKING:
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

AGENT_RUN_HOSTED_MODULE = "pipelex.cli.agent_cli.commands.run._run_hosted"
EXECUTION_MODULE = "pipelex.hosted.execution"
METHOD_REF = "github.com/Pipelex/methods/text_stats@v0.1.7"
STATS: dict[str, Any] = {"words": 4, "sentences": 2}
HOSTED_RESULTS: dict[str, Any] = {
    "pipeline_run_id": "run_7",
    "main_stuff": STATS,
    "working_memory": {
        "root": {"main_stuff": {"concept": "text_stats.Stats", "content": STATS, "stuff_code": "abc", "stuff_name": "main_stuff"}},
        "aliases": {},
    },
}


class TestRunHostedEnvelope:
    @pytest.fixture(autouse=True)
    def hosted_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_test_not_a_secret")
        monkeypatch.delenv(PIPELEX_BASE_URL_ENV_KEY, raising=False)
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

    @pytest.fixture
    def run_hosted(self, mocker: MockerFixture) -> AsyncMock:
        upload = UploadRecord(uri="pipelex-storage://uploads/a.pdf", filename="a.pdf", content_type="application/pdf", size=3)
        outcome = HostedRunOutcome(results=RunResults.model_validate(HOSTED_RESULTS), uploads=[upload])
        mocked: AsyncMock = mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(return_value=outcome))
        return mocked

    def test_compact_json_is_the_main_output(self, run_hosted: AsyncMock, capsys: pytest.CaptureFixture[str]) -> None:
        run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, inputs='{"text": "Hello world."}', output_format=CliOutputFormat.JSON)

        assert json.loads(capsys.readouterr().out) == STATS
        assert run_hosted.await_args is not None
        request = run_hosted.await_args.kwargs["request"]
        assert request.method_ref == METHOD_REF
        assert request.inputs == {"text": "Hello world."}

    def test_with_memory_carries_the_run_id_the_memory_and_the_uploads(self, run_hosted: AsyncMock, capsys: pytest.CaptureFixture[str]) -> None:
        run_method_cmd(name=METHOD_REF, hosted=True, with_memory=True, output_format=CliOutputFormat.JSON)

        run_hosted.assert_awaited_once()
        envelope = json.loads(capsys.readouterr().out)
        assert envelope["pipeline_run_id"] == "run_7"
        assert envelope["main_stuff"]["json"] == STATS
        assert envelope["working_memory"]["root"]["main_stuff"]["concept"] == "text_stats.Stats"
        assert envelope["uploads"][0]["uri"] == "pipelex-storage://uploads/a.pdf"

    def test_markdown_renders_the_main_output(self, run_hosted: AsyncMock, capsys: pytest.CaptureFixture[str]) -> None:
        run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.MARKDOWN)

        run_hosted.assert_awaited_once()
        markdown = capsys.readouterr().out
        assert markdown.startswith("# Pipeline run complete")
        assert '"sentences": 2' in markdown

    def test_the_configured_default_runs_hosted_without_a_flag(
        self, mocker: MockerFixture, run_hosted: AsyncMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mocker.patch(f"{EXECUTION_MODULE}.configured_run_execution", return_value=RunExecution.HOSTED)

        run_method_cmd(name=METHOD_REF, output_format=CliOutputFormat.JSON)

        run_hosted.assert_awaited_once()
        assert json.loads(capsys.readouterr().out) == STATS

    def test_a_failed_run_reports_its_stored_error(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A run that started and failed names the runner's class, its next step, its domain and the run."""
        report = RunErrorReport.model_validate(
            {
                "error_type": "LLMCompletionError",
                "message": "The provider refused the prompt",
                "error_domain": "runtime",
                "error_category": "transient",
                "retryable": True,
                "model": "claude-5.5-sonnet",
                "user_action": {"kind": "wait_and_retry", "detail": "Run it again in a minute"},
            }
        )
        failed = RunFailedError(
            "Run finished with status FAILED: The provider refused the prompt", run_id="run_9", status=RunStatus.FAILED, error=report
        )
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=failed))

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "LLMCompletionError"
        assert envelope["message"] == "Run finished with status FAILED: The provider refused the prompt"
        assert envelope["hint"] == "Run it again in a minute"
        assert envelope["error_domain"] == "runtime"
        assert envelope["error_category"] == "transient"
        assert envelope["retryable"] is True
        assert envelope["model"] == "claude-5.5-sonnet"
        assert envelope["pipeline_run_id"] == "run_9"
        assert envelope["run_status"] == "FAILED"
