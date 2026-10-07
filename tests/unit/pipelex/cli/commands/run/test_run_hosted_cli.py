"""Unit tests for `pipelex run method|pipe|bundle --hosted`: what each command sends, and what it saves.

`run_hosted` is mocked at the CLI seam, so no request leaves; the client is the real one, built from the flags and
the environment as a real run builds it.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from pipelex_sdk.error_models import RunErrorReport
from pipelex_sdk.errors import ApiUnreachableError, MissingMainStuffError, RunFailedError, RunTimeoutError
from pipelex_sdk.runs import RunResults, RunStatus
from pipelex_sdk.validation_models import ValidationErrorItem
from pydantic import ValidationError
from rich.console import Console
from typer.testing import CliRunner

from pipelex.cli._cli import app as pipelex_app
from pipelex.cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.commands.run.pipe_cmd import run_pipe_cmd
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.exceptions import HostedMethodInvalidError, HostedRunPollingError
from pipelex.hosted.hosted_run import HostedRunOutcome, HostedRunRequest
from pipelex.hosted.run_config import RunExecution
from pipelex.system.environment import PIPELEXPATH_ENV_KEY

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

RUN_HOSTED_MODULE = "pipelex.cli.commands.run._run_hosted"
RUN_CORE_MODULE = "pipelex.cli.commands.run._run_core"
BUNDLE_CMD_MODULE = "pipelex.cli.commands.run.bundle_cmd"
PIPE_CMD_MODULE = "pipelex.cli.commands.run.pipe_cmd"
EXECUTION_MODULE = "pipelex.hosted.execution"
ROOT_CLI_MODULE = "pipelex.cli._cli"
TEXT_STATS_REF = "github.com/Pipelex/methods/text_stats@v0.1.7"
LABELLED_ITEM = ValidationErrorItem.model_validate(
    {"category": "blueprint_validation", "message": "unknown concept Foo", "source": "lib/b.mthds", "pipe_code": "step2"}
)

BUNDLE = """domain = "probe"
main_pipe = "summarize"

[pipe.summarize]
type = "PipeLLM"
description = "Summarize"
inputs = { text = "Text" }
output = "Text"
prompt = "Summarize $text"
"""
LIBRARY_BUNDLE = 'domain = "probe_lib"\n'
REPORT_TEXT = "# Report\n\nAll good."
HOSTED_RESULTS: dict[str, Any] = {
    "pipeline_run_id": "run_42",
    "main_stuff": {"text": REPORT_TEXT},
    "graph_spec": {"graph_id": "run_42", "nodes": [], "edges": []},
    "working_memory": {
        "root": {"main_stuff": {"concept": "native.Text", "content": {"text": REPORT_TEXT}, "stuff_code": "abc", "stuff_name": "main_stuff"}},
        "aliases": {},
    },
}


def _results_body_drift() -> ValidationError:
    """The pydantic error a results body that drifted from the SDK's model raises when it is read."""
    try:
        RunResults.model_validate({"main_stuff": 1})
    except ValidationError as drift:
        return drift
    msg = "the drifted body validated"
    raise AssertionError(msg)


def _hosted_request(*, run_hosted: AsyncMock) -> HostedRunRequest:
    assert run_hosted.await_args is not None
    request = run_hosted.await_args.kwargs["request"]
    assert isinstance(request, HostedRunRequest)
    return request


class TestRunHostedCli:
    @pytest.fixture(autouse=True)
    def no_hosted_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(PIPELEX_BASE_URL_ENV_KEY, raising=False)
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_test_not_a_secret")

    @pytest.fixture
    def run_hosted(self, mocker: MockerFixture) -> AsyncMock:
        outcome = HostedRunOutcome(results=RunResults.model_validate(HOSTED_RESULTS))
        mocked: AsyncMock = mocker.patch(f"{RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(return_value=outcome))
        return mocked

    @pytest.fixture
    def bundle_dir(self, tmp_path: Path) -> Path:
        """A pipeline directory with its bundle and a second library file beside it."""
        pipeline_dir = tmp_path / "pipeline"
        pipeline_dir.mkdir()
        (pipeline_dir / "bundle.mthds").write_text(BUNDLE, encoding="utf-8")
        (pipeline_dir / "lib.mthds").write_text(LIBRARY_BUNDLE, encoding="utf-8")
        return pipeline_dir

    def test_bundle_sends_the_bundle_first_then_its_library_and_saves_the_outputs(
        self, run_hosted: AsyncMock, bundle_dir: Path, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "results"

        run_bundle_cmd(path=str(bundle_dir), hosted=True, output_dir=str(output_dir), no_pretty_print=True)

        request = _hosted_request(run_hosted=run_hosted)
        assert request.pipe_code == "summarize"
        assert [mthds_file.content for mthds_file in request.mthds_files or []] == [BUNDLE, LIBRARY_BUNDLE]
        assert request.method_ref is None
        assert request.method_id is None
        saved_dir = output_dir / "summarize_output_01"
        assert json.loads((saved_dir / "main_stuff.json").read_text(encoding="utf-8")) == {"text": REPORT_TEXT}
        assert (saved_dir / "main_stuff.md").read_text(encoding="utf-8") == REPORT_TEXT
        assert json.loads((saved_dir / "working_memory.json").read_text(encoding="utf-8"))["root"]["main_stuff"]["concept"] == "native.Text"
        assert json.loads((saved_dir / "graphspec.json").read_text(encoding="utf-8"))["graph_id"] == "run_42"

    def test_no_graph_saves_no_graphspec(self, run_hosted: AsyncMock, bundle_dir: Path, tmp_path: Path) -> None:
        run_bundle_cmd(path=str(bundle_dir), hosted=True, output_dir=str(tmp_path / "results"), graph=False, no_pretty_print=True)

        run_hosted.assert_awaited_once()
        assert not (tmp_path / "results" / "summarize_output_01" / "graphspec.json").exists()

    @pytest.mark.parametrize(
        ("name", "expected_method_ref", "expected_method_id"),
        [
            ("github.com/Pipelex/methods/text_stats@v0.1.7", "github.com/Pipelex/methods/text_stats@v0.1.7", None),
            ("https://github.com/Pipelex/methods/tree/main/text_stats", "github.com/Pipelex/methods/text_stats", None),
            ("mt_abc123", None, "mt_abc123"),
        ],
    )
    def test_method_named_remotely_is_resolved_by_the_hosted_api(
        self,
        mocker: MockerFixture,
        run_hosted: AsyncMock,
        tmp_path: Path,
        name: str,
        expected_method_ref: str | None,
        expected_method_id: str | None,
    ) -> None:
        """An address and a catalog id are sent as names: nothing is fetched or read on this machine."""
        fetch = mocker.patch("pipelex.cli.method_resolver.fetch_method_package", side_effect=AssertionError("fetched"))

        run_method_cmd(name=name, hosted=True, inputs='{"text": "Hello"}', output_dir=str(tmp_path), no_pretty_print=True)

        request = _hosted_request(run_hosted=run_hosted)
        assert request.method_ref == expected_method_ref
        assert request.method_id == expected_method_id
        assert request.mthds_files is None
        assert request.pipe_code is None
        assert request.inputs == {"text": "Hello"}
        fetch.assert_not_called()

    def test_an_inputs_file_anchors_its_relative_paths_to_its_directory(self, run_hosted: AsyncMock, tmp_path: Path) -> None:
        inputs_dir = tmp_path / "inputs"
        inputs_dir.mkdir()
        (inputs_dir / "inputs.json").write_text('{"document": "invoice.pdf"}', encoding="utf-8")

        run_method_cmd(
            name="github.com/Pipelex/methods/documents@v0.1.7",
            pipe="extract_document_text",
            hosted=True,
            inputs=str(inputs_dir / "inputs.json"),
            output_dir=str(tmp_path),
            no_pretty_print=True,
        )

        request = _hosted_request(run_hosted=run_hosted)
        assert request.pipe_code == "extract_document_text"
        assert request.inputs_base_dir == inputs_dir.resolve()

    def test_the_configured_default_runs_hosted_and_local_overrides_it(
        self, mocker: MockerFixture, run_hosted: AsyncMock, bundle_dir: Path, tmp_path: Path
    ) -> None:
        """`[run] execution = "hosted"` sends a run with no flag; `--local` keeps the run on this machine."""
        mocker.patch(f"{EXECUTION_MODULE}.configured_run_execution", return_value=RunExecution.HOSTED)
        local_run = mocker.patch(f"{BUNDLE_CMD_MODULE}.execute_run")

        run_bundle_cmd(path=str(bundle_dir), output_dir=str(tmp_path), no_pretty_print=True)
        run_hosted.assert_awaited_once()
        local_run.assert_not_called()

        run_bundle_cmd(path=str(bundle_dir), hosted=False, output_dir=str(tmp_path), no_pretty_print=True)
        local_run.assert_called_once()
        run_hosted.assert_awaited_once()

    @pytest.mark.parametrize(
        "flags",
        [
            {"hosted": True, "dry_run": True},
            {"hosted": True, "orchestrator": "temporal"},
            {"hosted": True, "save_csv": "out.csv"},
            {"hosted": True, "costs": False},
            {"hosted": True, "graph_full_data": True},
            {"hosted": False, "base_url": "https://api.pipelex.com"},
            {"hosted": True, "base_url": "https://api.pipelex.com/v1"},
        ],
    )
    def test_local_only_flags_and_a_misplaced_base_url_are_refused(
        self, mocker: MockerFixture, run_hosted: AsyncMock, bundle_dir: Path, flags: dict[str, Any]
    ) -> None:
        local_run = mocker.patch(f"{BUNDLE_CMD_MODULE}.execute_run")

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_dir), **flags)

        assert exc_info.value.exit_code == 1
        run_hosted.assert_not_awaited()
        local_run.assert_not_called()

    def test_a_pipe_run_with_no_library_is_refused(self, mocker: MockerFixture, run_hosted: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PIPELEXPATH", raising=False)
        mocker.patch(f"{PIPE_CMD_MODULE}.resolve_pipe_from_exports", return_value=None)

        with pytest.raises(typer.Exit) as exc_info:
            run_pipe_cmd(pipe_code="summarize", hosted=True)

        assert exc_info.value.exit_code == 1
        run_hosted.assert_not_awaited()

    def test_a_pipe_run_sends_its_library(self, mocker: MockerFixture, run_hosted: AsyncMock, bundle_dir: Path, tmp_path: Path) -> None:
        mocker.patch(f"{PIPE_CMD_MODULE}.resolve_pipe_from_exports", return_value=None)

        run_pipe_cmd(pipe_code="summarize", hosted=True, library_dir=[str(bundle_dir)], output_dir=str(tmp_path), no_pretty_print=True)

        request = _hosted_request(run_hosted=run_hosted)
        assert request.pipe_code == "summarize"
        assert sorted(mthds_file.content for mthds_file in request.mthds_files or []) == sorted([BUNDLE, LIBRARY_BUNDLE])

    def test_a_hosted_failure_exits_with_its_next_step(self, mocker: MockerFixture, bundle_dir: Path) -> None:
        unreachable = ApiUnreachableError("Could not reach Pipelex API at https://api.pipelex.com (ConnectError)", api_url="https://api.pipelex.com")
        mocker.patch(f"{RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=unreachable))
        print_failure = mocker.patch(f"{RUN_HOSTED_MODULE}._print_hosted_failure")

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_dir), hosted=True)

        assert exc_info.value.exit_code == 1
        print_failure.assert_called_once_with(error=unreachable)

    def test_a_bundle_file_without_a_library_sends_pipelexpath(
        self, monkeypatch: pytest.MonkeyPatch, run_hosted: AsyncMock, bundle_dir: Path, tmp_path: Path
    ) -> None:
        """A local run of a bundle file loads PIPELEXPATH when no -L is given; a hosted one sends it."""
        shared_dir = tmp_path / "shared"
        shared_dir.mkdir()
        (shared_dir / "shared.mthds").write_text(LIBRARY_BUNDLE, encoding="utf-8")
        monkeypatch.setenv(PIPELEXPATH_ENV_KEY, str(shared_dir))

        run_bundle_cmd(path=str(bundle_dir / "bundle.mthds"), hosted=True, output_dir=str(tmp_path / "results"), no_pretty_print=True)

        request = _hosted_request(run_hosted=run_hosted)
        assert [mthds_file.source for mthds_file in request.mthds_files or []] == [str(bundle_dir / "bundle.mthds"), str(shared_dir / "shared.mthds")]

    def test_a_named_text_output_is_saved_as_markdown_too(self, mocker: MockerFixture, bundle_dir: Path, tmp_path: Path) -> None:
        """The working memory names the main output through its `main_stuff` alias when a step named it."""
        named = RunResults.model_validate(
            {
                "pipeline_run_id": "run_6",
                "main_stuff": {"text": REPORT_TEXT},
                "working_memory": {
                    "root": {"summary": {"concept": "native.Text", "content": {"text": REPORT_TEXT}}},
                    "aliases": {"main_stuff": "summary"},
                },
            }
        )
        mocker.patch(f"{RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(return_value=HostedRunOutcome(results=named)))
        output_dir = tmp_path / "results"

        run_bundle_cmd(path=str(bundle_dir), hosted=True, output_dir=str(output_dir), no_pretty_print=True)

        assert (output_dir / "summarize_output_01" / "main_stuff.md").read_text(encoding="utf-8") == REPORT_TEXT

    def test_an_unexpected_failure_exits_with_a_failure_line(self, mocker: MockerFixture, bundle_dir: Path) -> None:
        """A failure no hosted arm names, such as a results body that drifted, is a failure line and exit 1, not a traceback."""
        output = io.StringIO()
        mocker.patch(f"{RUN_HOSTED_MODULE}.get_console", return_value=Console(file=output, width=250))
        mocker.patch(f"{RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=_results_body_drift()))

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_dir), hosted=True)

        assert exc_info.value.exit_code == 1
        printed = output.getvalue()
        assert "Failed to run on the hosted API" in printed
        assert "ValidationError" in printed
        assert "Traceback" not in printed

    @pytest.mark.parametrize(
        ("error", "expected_lines"),
        [
            (
                RunFailedError(
                    "Run finished with status FAILED: bundle invalid",
                    run_id="run_9",
                    status=RunStatus.FAILED,
                    error=RunErrorReport.model_validate(
                        {
                            "error_type": "ValidateBundleError",
                            "message": "bundle invalid",
                            "validation_errors": [LABELLED_ITEM.model_dump(mode="json")],
                        }
                    ),
                ),
                ["lib/b.mthds: unknown concept Foo", "Run id: run_9"],
            ),
            (
                HostedMethodInvalidError("The hosted API cannot load the method: Bundle does not load", validation_errors=[LABELLED_ITEM]),
                ["lib/b.mthds: unknown concept Foo"],
            ),
            (
                HostedRunPollingError("The run run_7 started on the hosted API, but following it failed", pipeline_run_id="run_7"),
                ["Run id: run_7", "may still be running"],
            ),
            (RunTimeoutError("Run 'run_7' did not finish within 1200s", run_id="run_7", timeout_seconds=1200.0), ["Run id: run_7"]),
            (MissingMainStuffError("Completed run 'run_7' returned no main stuff", run_id="run_7"), ["Run id: run_7"]),
        ],
    )
    def test_a_hosted_failure_prints_its_items_and_its_run(
        self, mocker: MockerFixture, bundle_dir: Path, error: Exception, expected_lines: list[str]
    ) -> None:
        output = io.StringIO()
        mocker.patch(f"{RUN_HOSTED_MODULE}.get_console", return_value=Console(file=output, width=250))
        mocker.patch(f"{RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock(side_effect=error))

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_dir), hosted=True)

        printed = output.getvalue()
        for expected_line in expected_lines:
            assert expected_line in printed

    def test_a_hosted_run_prints_no_deck_notice_and_a_local_run_does(self, mocker: MockerFixture, run_hosted: AsyncMock, tmp_path: Path) -> None:
        """The deck notice is about this machine's inference, which a hosted run never boots."""
        mocker.patch(f"{ROOT_CLI_MODULE}.check_readiness")
        root_notice = mocker.patch(f"{ROOT_CLI_MODULE}.warn_if_deck_stale")
        run_notice = mocker.patch(f"{RUN_CORE_MODULE}.warn_if_deck_stale")
        mocker.patch(f"{RUN_CORE_MODULE}.make_pipelex_for_cli", side_effect=typer.Exit(3))

        hosted = CliRunner().invoke(
            pipelex_app,
            ["--no-logo", "run", "method", TEXT_STATS_REF, "--hosted", "--inputs", '{"text": "x"}', "-o", str(tmp_path), "--no-pretty-print"],
        )
        assert hosted.exit_code == 0, hosted.output
        run_hosted.assert_awaited_once()
        root_notice.assert_not_called()
        run_notice.assert_not_called()

        local = CliRunner().invoke(pipelex_app, ["--no-logo", "run", "pipe", "summarize", "--local", "-L", str(tmp_path)])
        assert local.exit_code == 3, local.output
        run_notice.assert_called_once()
        root_notice.assert_not_called()

    def test_every_other_command_still_prints_the_deck_notice(self, mocker: MockerFixture) -> None:
        mocker.patch(f"{ROOT_CLI_MODULE}.check_readiness")
        root_notice = mocker.patch(f"{ROOT_CLI_MODULE}.warn_if_deck_stale")

        CliRunner().invoke(pipelex_app, ["--no-logo", "validate", "--help"])

        root_notice.assert_called_once()
