"""Unit tests for `pipelex run method|pipe|bundle --hosted`: what each command sends, and what it saves.

`run_hosted` is mocked at the CLI seam, so no request leaves; the client is the real one, built from the flags and
the environment as a real run builds it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from pipelex_sdk.errors import ApiUnreachableError
from pipelex_sdk.runs import RunResults

from pipelex.cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.commands.run.pipe_cmd import run_pipe_cmd
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.hosted_run import HostedRunOutcome, HostedRunRequest
from pipelex.hosted.run_config import RunExecution

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

RUN_HOSTED_MODULE = "pipelex.cli.commands.run._run_hosted"
BUNDLE_CMD_MODULE = "pipelex.cli.commands.run.bundle_cmd"
PIPE_CMD_MODULE = "pipelex.cli.commands.run.pipe_cmd"
EXECUTION_MODULE = "pipelex.hosted.execution"

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
