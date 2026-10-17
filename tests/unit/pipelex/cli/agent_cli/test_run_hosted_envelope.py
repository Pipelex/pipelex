"""Unit tests: `pipelex-agent run … --runner hosted` answers in the run envelope a local run answers in, and fails with a problem.

`run_hosted` is mocked at the agent CLI seam, so no request leaves.
"""

from __future__ import annotations

import asyncio
import io
import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from mthds.protocol.problem.registry import CoreCode
from pipelex_sdk.error_models import RunErrorReport
from pipelex_sdk.errors import MissingMainStuffError, RunFailedError, RunTimeoutError
from pipelex_sdk.runs import RunResults, RunStatus
from pipelex_sdk.upload import UploadRecord
from pipelex_sdk.validation_models import ValidationErrorItem
from pydantic import ValidationError

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd
from pipelex.errors.problem import ProblemView, make_problem
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.exceptions import HostedMethodInvalidError, HostedRunPollingError
from pipelex.hosted.hosted_run import HostedRunOutcome, HostedRunRequest
from pipelex.hosted.run_config import RunExecution
from pipelex.system.environment import PIPELEXPATH_ENV_KEY
from tests.unit.pipelex.cli.agent_cli.test_data import HostedMethodItems, RetiredEnvelope, StoredRunReports

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

    @pytest.mark.parametrize("error_format", [CliOutputFormat.JSON, CliOutputFormat.MARKDOWN])
    def test_a_failed_run_is_run_failed_naming_the_run(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], error_format: CliOutputFormat
    ) -> None:
        """A run that started and failed is the client's `run.failed`, naming the run and its status, with its stored reason."""
        report = RunErrorReport.model_validate(StoredRunReports.FORMER_SHAPE)
        failed = RunFailedError(
            "Run finished with status FAILED: The provider refused the prompt", run_id="run_9", status=RunStatus.FAILED, error=report
        )
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=failed))

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=error_format)

        assert exc_info.value.exit_code == 1
        printed = capsys.readouterr().err
        match error_format:
            case CliOutputFormat.JSON:
                problem = json.loads(printed)
                assert problem == {
                    **failed.problem.as_wire(),
                    "message": "Run finished with status FAILED: The provider refused the prompt",
                }
                assert problem["code"] == "run.failed"
                assert problem["params"] == {"pipeline_run_id": "run_9", "run_status": "FAILED"}
                assert problem["pipeline_run_id"] == "run_9"
                # The report is in the former shape, so no problem of the run's own is nested.
                assert "run_error" not in problem
                for retired in RetiredEnvelope.MEMBERS:
                    assert retired not in problem
            case CliOutputFormat.MARKDOWN:
                assert printed.startswith(f"## {failed.problem.title}\n")
                assert "Run finished with status FAILED: The provider refused the prompt" in printed
                assert "- Run: `run_9`" in printed
                assert "LLMCompletionError" not in printed

    @pytest.mark.parametrize(
        "stored_report",
        [StoredRunReports.PROBLEM, StoredRunReports.PROBLEM_WITH_REPORT_MEMBERS],
        ids=["problem", "problem_with_report_members"],
    )
    def test_a_failed_run_nests_the_run_s_own_problem_in_the_caller_s_view(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], stored_report: dict[str, Any]
    ) -> None:
        """A stored report that is a problem document rides as `run_error` by its declared members alone, without the
        diagnostics only its operator reads, and a member it holds in a shape this version does not read drops only itself.
        """
        report = RunErrorReport.model_validate(stored_report)
        failed = RunFailedError("Run finished with status FAILED", run_id="run_9", status=RunStatus.FAILED, error=report)
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=failed))

        with pytest.raises(typer.Exit):
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "run.failed"
        stored = {name: value for name, value in StoredRunReports.PROBLEM.items() if name != "diagnostics"}
        assert problem["run_error"] == stored

    def test_a_failed_run_s_own_problem_in_markdown(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        report = RunErrorReport.model_validate(StoredRunReports.PROBLEM)
        failed = RunFailedError("Run finished with status FAILED", run_id="run_9", status=RunStatus.FAILED, error=report)
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=failed))

        with pytest.raises(typer.Exit):
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.MARKDOWN)

        markdown = capsys.readouterr().err
        assert "### The run's own problem" in markdown
        assert (
            "**A pipe's output does not have the declared multiplicity**: Pipe 'review_topic' produced an output of the multiplicity "
            "'list', but its output 'ideas' is declared 'single'."
        ) in markdown
        assert "- Code: `pipe.output_multiplicity` (domain method, retry no)" in markdown
        assert "PipeOutputMultiplicityError" not in markdown

    def test_a_pipelex_error_no_hosted_arm_names_reports_its_own_code(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A Pipelex error of this process's that is no hosted run's leaves as a local failure does, under its own code in the operator's view."""
        config_error = PipelexConfigError("pipelex.toml is invalid")
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=config_error))

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "pipelex.config.invalid"
        assert problem["next_step"] == config_error.to_problem(view=ProblemView.OPERATOR).next_step.as_wire()
        assert problem["diagnostics"]["error_class"] == "PipelexConfigError"

    def test_an_unexpected_failure_is_this_process_s_own_problem(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """A failure no hosted arm names, such as a results body that drifted, is `runtime.unexpected`, as a local run reports it."""
        with pytest.raises(ValidationError) as drift:
            RunResults.model_validate({"main_stuff": 1})
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=drift.value))

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "runtime.unexpected"
        assert problem["next_step"] == make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR).next_step.as_wire()
        assert problem["diagnostics"]["error_class"] == "ValidationError"
        for retired in RetiredEnvelope.MEMBERS:
            assert retired not in problem

    @pytest.mark.parametrize("interruption", [KeyboardInterrupt(), asyncio.CancelledError()])
    def test_an_interrupted_run_names_the_run_and_exits_130(
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
        problem = json.loads(captured.err)
        assert problem["code"] == "client.follow_failed"
        assert problem["pipeline_run_id"] == "run_77"
        assert problem["params"] == {"pipeline_run_id": "run_77"}
        assert problem["next_step"] == {"kind": "read_run", "detail": "Read the run 'run_77' by its id rather than start it again."}
        assert "keeps going on the hosted API" in problem["message"]
        assert "diagnostics" not in problem

    def test_a_run_interrupted_before_its_acknowledgement_leaves_the_outcome_unknown(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=KeyboardInterrupt()))

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 130
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "client.outcome_unknown"
        assert "pipeline_run_id" not in problem

    @pytest.mark.parametrize(
        ("error", "code", "message"),
        [
            (
                RunTimeoutError("Run 'run_7' did not finish within 1200s", run_id="run_7", timeout_seconds=1200.0),
                "run.not_finished",
                "Run 'run_7' did not finish within 1200s",
            ),
            (
                MissingMainStuffError("Completed run 'run_7' returned no main stuff", run_id="run_7"),
                "client.response_unreadable",
                "Completed run 'run_7' returned no main stuff",
            ),
            (
                HostedRunPollingError("The run run_7 started on the hosted API, but following it failed", pipeline_run_id="run_7"),
                "client.follow_failed",
                "The run run_7 started on the hosted API, but following it failed",
            ),
        ],
        ids=["timed_out", "no_main_output", "follow_failed"],
    )
    @pytest.mark.parametrize("error_format", [CliOutputFormat.JSON, CliOutputFormat.MARKDOWN])
    def test_an_error_after_the_start_carries_the_run_id_and_what_the_client_said(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], error: Exception, code: str, message: str, error_format: CliOutputFormat
    ) -> None:
        """The client's sentence says what the code cannot (how long it waited, that a completed run delivered nothing): it is the `message`."""
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=error))

        with pytest.raises(typer.Exit):
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=error_format)

        printed = capsys.readouterr().err
        match error_format:
            case CliOutputFormat.JSON:
                problem = json.loads(printed)
                assert problem["code"] == code
                assert problem["pipeline_run_id"] == "run_7"
                assert problem["message"] == message
                for retired in RetiredEnvelope.MEMBERS:
                    assert retired not in problem
            case CliOutputFormat.MARKDOWN:
                assert message in printed
                assert f"- Code: `{code}`" in printed

    def test_a_method_that_does_not_load_lists_the_hosted_api_s_items(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Each item of pipe-io's verdict is a problem item coded as a local verdict codes it, located in the file it was sent as."""
        refused = HostedMethodInvalidError(
            "The hosted API cannot load the method: Bundle does not load",
            validation_errors=[ValidationErrorItem.model_validate(item) for item in HostedMethodItems.SENT],
        )
        mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=refused))

        with pytest.raises(typer.Exit):
            run_method_cmd(name=METHOD_REF, runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "method.invalid"
        assert problem["errors"] == HostedMethodItems.PROBLEM_ITEMS
        assert problem["message"] == "The hosted API cannot load the method: Bundle does not load"
        for retired in RetiredEnvelope.MEMBERS:
            assert retired not in problem

    def test_a_configuration_that_cannot_be_read_gives_the_boot_s_problem(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Reading `[run] execution` meets the configuration a local boot meets, and reports the problem a local boot reports."""
        config_error = PipelexConfigError("pipelex.toml is invalid")
        mocker.patch(f"{EXECUTION_MODULE}.configured_run_execution", side_effect=config_error)

        with pytest.raises(typer.Exit):
            run_method_cmd(name=METHOD_REF, output_format=CliOutputFormat.JSON)

        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "pipelex.config.invalid"
        assert problem["domain"] == "operator"
        assert problem["next_step"] == config_error.to_problem(view=ProblemView.OPERATOR).next_step.model_dump(mode="json", exclude_none=True)
        assert problem["diagnostics"]["error_class"] == "PipelexConfigError"
        assert "error_type" not in problem

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

    def test_a_folder_run_names_its_main_pipe_by_its_domain_when_two_domains_share_its_code(
        self, run_hosted: AsyncMock, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The hosted API starts at the pipe the local run would, never at a same-coded pipe of another domain sent with it."""
        pipe_table = (
            '[pipe.summarize]\ntype = "PipeLLM"\ndescription = "Summarize"\ninputs = { text = "Text" }\noutput = "Text"\nprompt = "Summarize $text"\n'
        )
        (tmp_path / "a_first.mthds").write_text(f'domain = "probe_other"\n\n{pipe_table}', encoding="utf-8")
        (tmp_path / "z_entry.mthds").write_text(f'domain = "probe_entry"\nmain_pipe = "summarize"\n\n{pipe_table}', encoding="utf-8")

        run_bundle_cmd(path=str(tmp_path), runner=RunExecution.HOSTED, output_format=CliOutputFormat.JSON)

        capsys.readouterr()
        assert run_hosted.await_args is not None
        request = run_hosted.await_args.kwargs["request"]
        assert isinstance(request, HostedRunRequest)
        assert request.pipe_code == "probe_entry.summarize"
