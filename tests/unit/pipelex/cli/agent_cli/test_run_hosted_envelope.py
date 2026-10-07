"""Unit tests: `pipelex-agent run … --runner hosted` answers in the run envelope a local run answers in.

`run_hosted` is mocked at the agent CLI seam, so no request leaves.
"""

from __future__ import annotations

import asyncio
import io
import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from pipelex_sdk.error_models import RunErrorReport
from pipelex_sdk.errors import MissingMainStuffError, RunFailedError, RunTimeoutError
from pipelex_sdk.runs import RunResults, RunStatus
from pipelex_sdk.upload import UploadRecord
from pipelex_sdk.validation_models import ValidationErrorItem
from pydantic import ValidationError

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.agent_cli.commands.agent_cli_factory import AGENT_INIT_FAILURE_HINT
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.exceptions import HostedMethodInvalidError, HostedRunPollingError
from pipelex.hosted.hosted_run import HostedRunOutcome, HostedRunRequest
from pipelex.hosted.run_config import RunExecution
from pipelex.system.environment import PIPELEXPATH_ENV_KEY

if TYPE_CHECKING:
    from pathlib import Path
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

    def test_an_unexpected_failure_is_an_envelope(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A failure no hosted arm names, such as a results body that drifted, still leaves as the JSON envelope."""
        with pytest.raises(ValidationError) as drift:
            RunResults.model_validate({"main_stuff": 1})
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=drift.value))

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error"] is True
        assert envelope["error_type"] == "ValidationError"

    def test_a_hosted_verdict_that_the_failure_is_not_retryable_wins_over_the_local_table(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The local table calls this class retryable; the hosted runner said it is not, and only it knows."""
        report = RunErrorReport.model_validate(
            {
                "error_type": "PipeOperatorModelAvailabilityError",
                "message": "no model available for the pipe",
                "error_domain": "config",
                "retryable": False,
            }
        )
        failed = RunFailedError(
            "Run finished with status FAILED: no model available for the pipe", run_id="run_f3", status=RunStatus.FAILED, error=report
        )
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=failed))

        with pytest.raises(typer.Exit):
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "PipeOperatorModelAvailabilityError"
        assert envelope["retryable"] is False
        assert envelope["error_domain"] == "config"

    @pytest.mark.parametrize("interruption", [KeyboardInterrupt(), asyncio.CancelledError()])
    def test_an_interrupted_run_is_an_envelope_naming_the_run_and_exits_130(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], interruption: BaseException
    ) -> None:
        def _started_then_interrupted(**kwargs: Any) -> HostedRunOutcome:
            kwargs["on_started"](pipeline_run_id="run_77")
            raise interruption

        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=_started_then_interrupted))

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 130
        captured = capsys.readouterr()
        assert captured.out == ""
        envelope = json.loads(captured.err)
        assert envelope["error_type"] == "HostedRunInterruptedError"
        assert envelope["pipeline_run_id"] == "run_77"
        assert "keeps going on the hosted API" in envelope["message"]
        assert "run_77" in envelope["hint"]

    @pytest.mark.parametrize(
        "error",
        [
            RunTimeoutError("Run 'run_7' did not finish within 1200s", run_id="run_7", timeout_seconds=1200.0),
            MissingMainStuffError("Completed run 'run_7' returned no main stuff", run_id="run_7"),
            HostedRunPollingError("The run run_7 started on the hosted API, but following it failed", pipeline_run_id="run_7"),
        ],
    )
    def test_an_error_after_the_start_carries_the_run_id(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], error: Exception) -> None:
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=error))

        with pytest.raises(typer.Exit):
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == type(error).__name__
        assert envelope["pipeline_run_id"] == "run_7"
        assert "run_7" in envelope["hint"]

    def test_a_method_that_does_not_load_lists_its_labelled_items(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        item = ValidationErrorItem.model_validate(
            {"category": "blueprint_validation", "message": "unknown concept Foo", "source": "lib/b.mthds", "pipe_code": "step2"}
        )
        refused = HostedMethodInvalidError("The hosted API cannot load the method: Bundle does not load", validation_errors=[item])
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=refused))

        with pytest.raises(typer.Exit):
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "HostedMethodInvalidError"
        assert envelope["error_domain"] == "input"
        assert envelope["validation_errors"][0]["source"] == "lib/b.mthds"
        assert envelope["validation_errors"][0]["message"] == "unknown concept Foo"

    def test_a_configuration_that_cannot_be_read_gives_the_boot_hint(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Reading `[run] execution` meets the configuration a local boot meets, and says what a local boot says."""
        mocker.patch(f"{EXECUTION_MODULE}.configured_run_execution", side_effect=PipelexConfigError("pipelex.toml is invalid"))

        with pytest.raises(typer.Exit):
            run_method_cmd(name=METHOD_REF, output_format=CliOutputFormat.JSON)

        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "PipelexConfigError"
        assert envelope["hint"] == AGENT_INIT_FAILURE_HINT

    def test_a_bundle_file_without_a_library_sends_pipelexpath(
        self, monkeypatch: pytest.MonkeyPatch, run_hosted: AsyncMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bundle_path = tmp_path / "bundle.mthds"
        bundle_path.write_text('domain = "probe"\nmain_pipe = "entry"\n', encoding="utf-8")
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir()
        (shared_dir / "shared.mthds").write_text('domain = "probe_lib"\n', encoding="utf-8")
        monkeypatch.setenv(PIPELEXPATH_ENV_KEY, str(shared_dir))

        run_bundle_cmd(path=str(bundle_path), pipe="entry", runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        capsys.readouterr()
        assert run_hosted.await_args is not None
        request = run_hosted.await_args.kwargs["request"]
        assert isinstance(request, HostedRunRequest)
        assert [mthds_file.source for mthds_file in request.mthds_files or []] == [str(bundle_path), str(shared_dir / "shared.mthds")]
