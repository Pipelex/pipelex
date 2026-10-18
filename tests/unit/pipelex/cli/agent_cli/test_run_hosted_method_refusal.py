from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.run_config import RunExecution
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsError, UsageStatsErrorDomain
from tests.unit.pipelex.cli.agent_cli.test_data import RefusedBundles, RetiredEnvelope

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import AsyncMock

    from pytest_mock import MockerFixture

AGENT_RUN_HOSTED_MODULE = "pipelex.cli.agent_cli.commands.run._run_hosted"
AGENT_OUTPUT_MODULE = "pipelex.cli.agent_cli.commands.agent_output"
#: The caller's step of `method.invalid`, the verdict's code.
VERDICT_STEP: dict[str, str] = {"kind": "change_method", "detail": "Fix each fault the problem's errors list, then validate the method again."}


def _assert_nothing_only_an_operator_reads(*, reported: str) -> None:
    """No Pipelex class name, no member of the operator's view and no source path in what the caller reads."""
    for operator_only in RefusedBundles.OPERATOR_ONLY:
        assert operator_only not in reported, operator_only
    assert ".py" not in reported


def _item_entries(*, markdown: str) -> list[str]:
    """The entries of the Markdown's `### Errors` section, one per item, each from its code to the next item.

    An item's sentence may quote text on several lines, such as a template's source, so an entry is cut at the next
    item's bullet rather than at the end of its first line.
    """
    errors_section = markdown.split("### Errors\n\n", 1)[1]
    return [f"- `{entry}" if index_entry else entry for index_entry, entry in enumerate(errors_section.split("\n- `"))]


def _write_bundle(*, directory: Path, source: str) -> Path:
    bundle_path = directory / "bundle.mthds"
    bundle_path.write_text(source, encoding="utf-8")
    return bundle_path


class TestRunHostedMethodRefusal:
    @pytest.fixture(autouse=True)
    def hosted_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_test_not_a_secret")
        monkeypatch.delenv(PIPELEX_BASE_URL_ENV_KEY, raising=False)
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

    @pytest.fixture
    def run_hosted(self, mocker: MockerFixture) -> AsyncMock:
        """The run on the runner, which a method refused before it is sent never reaches."""
        mocked: AsyncMock = mocker.patch(f"{AGENT_RUN_HOSTED_MODULE}.run_hosted", new=mocker.AsyncMock())
        return mocked

    @pytest.mark.parametrize(("case_id", "source", "item_codes", "item_places"), RefusedBundles.CASES, ids=[case[0] for case in RefusedBundles.CASES])
    def test_json_is_the_caller_s_view_of_the_verdict(
        self,
        run_hosted: AsyncMock,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
        case_id: str,
        source: str,
        item_codes: list[str],
        item_places: list[dict[str, Any]],
    ) -> None:
        """The JSON keeps the code, the items with their places and the caller's step, and holds nothing only an operator reads."""
        bundle_path = _write_bundle(directory=tmp_path, source=source)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_path), inputs="{}", runner=RunExecution.HOSTED, error_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1, case_id
        run_hosted.assert_not_awaited()
        captured = capsys.readouterr()
        assert not captured.out
        problem = json.loads(captured.err)
        assert problem["code"] == "method.invalid"
        assert problem["domain"] == "method"
        assert problem["retry"] == "no"
        assert problem["next_step"] == VERDICT_STEP
        assert [item["code"] for item in problem["errors"]] == item_codes
        for item, place in zip(problem["errors"], item_places, strict=True):
            assert item["location"] == {**place, "file": str(bundle_path)}
            assert item["detail"]
        assert "message" not in problem
        for retired in RetiredEnvelope.MEMBERS:
            assert retired not in problem
        _assert_nothing_only_an_operator_reads(reported=captured.err)

    @pytest.mark.parametrize(("case_id", "source", "item_codes", "item_places"), RefusedBundles.CASES, ids=[case[0] for case in RefusedBundles.CASES])
    def test_markdown_is_the_caller_s_view_of_the_verdict(
        self,
        run_hosted: AsyncMock,
        capsys: pytest.CaptureFixture[str],
        tmp_path: Path,
        case_id: str,
        source: str,
        item_codes: list[str],
        item_places: list[dict[str, Any]],
    ) -> None:
        """The default Markdown lists the same items in their places, under the caller's step, with no Diagnostics section."""
        bundle_path = _write_bundle(directory=tmp_path, source=source)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_path), inputs="{}", runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1, case_id
        run_hosted.assert_not_awaited()
        captured = capsys.readouterr()
        assert not captured.out
        markdown = captured.err
        # The step follows the detail at once: the raise site's message, which the command quotes on a local run, is not
        # the caller's to read.
        assert markdown.startswith(
            f"## The method does not validate\n\nThe method does not validate.\n\n**Next step** (`change_method`): {VERDICT_STEP['detail']}\n"
        )
        assert "- Code: `method.invalid` (domain method, retry no)" in markdown
        entries = _item_entries(markdown=markdown)
        assert [entry.split("`", 2)[1] for entry in entries] == item_codes
        for entry, place in zip(entries, item_places, strict=True):
            assert f"file '{bundle_path}'" in entry
            if "pipe" in place:
                assert f"pipe '{place['pipe']}'" in entry
            if "line" in place:
                assert f"line {place['line']}, column {place['column']}" in entry
        assert "### Diagnostics" not in markdown
        assert "Error class" not in markdown
        _assert_nothing_only_an_operator_reads(reported=markdown)

    def test_a_folder_with_no_pipe_to_start_at_reads_in_the_caller_s_view(
        self, run_hosted: AsyncMock, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """A method with no single main pipe is refused before it is sent, as the runner would refuse it, naming no class."""
        _write_bundle(directory=tmp_path, source=RefusedBundles.NO_MAIN_PIPE)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(tmp_path), inputs="{}", runner=RunExecution.HOSTED, error_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        run_hosted.assert_not_awaited()
        reported = capsys.readouterr().err
        problem = json.loads(reported)
        assert problem["code"] == "request.pipe_unspecified"
        assert problem["next_step"]["kind"] == "change_input"
        assert "message" not in problem
        _assert_nothing_only_an_operator_reads(reported=reported)

    @pytest.mark.parametrize("error_format", [CliOutputFormat.JSON, CliOutputFormat.MARKDOWN])
    def test_a_bundle_file_with_no_main_pipe_reads_in_the_caller_s_view(
        self, run_hosted: AsyncMock, capsys: pytest.CaptureFixture[str], tmp_path: Path, error_format: CliOutputFormat
    ) -> None:
        """A bundle file named alone with no main pipe is the folder's refusal: its candidates kept, no message, no path."""
        bundle_path = _write_bundle(directory=tmp_path, source=RefusedBundles.NO_MAIN_PIPE)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_path), inputs="{}", runner=RunExecution.HOSTED, error_format=error_format)

        assert exc_info.value.exit_code == 1
        run_hosted.assert_not_awaited()
        captured = capsys.readouterr()
        assert not captured.out
        reported = captured.err
        assert str(tmp_path) not in reported
        assert "does not declare a main_pipe" not in reported
        _assert_nothing_only_an_operator_reads(reported=reported)
        match error_format:
            case CliOutputFormat.JSON:
                problem = json.loads(reported)
                assert problem["code"] == "request.pipe_unspecified"
                assert problem["domain"] == "input"
                assert problem["next_step"]["kind"] == "change_input"
                assert problem["params"] == {"candidates": ["say"]}
                assert "message" not in problem
            case CliOutputFormat.MARKDOWN:
                assert reported.startswith(
                    "## No pipe is selected\n\n"
                    "The request selects no pipe, and the method gives no main pipe to start from.\n\n"
                    "**Next step** (`change_input`): "
                )
                assert "- Code: `request.pipe_unspecified` (domain input, retry no)" in reported
                assert "### Diagnostics" not in reported

    def test_a_bundle_file_with_no_main_pipe_run_locally_keeps_its_sentence(
        self, run_hosted: AsyncMock, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """On this machine's runtime the same refusal keeps its code, its candidates and the command's sentence naming the file."""
        bundle_path = _write_bundle(directory=tmp_path, source=RefusedBundles.NO_MAIN_PIPE)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_path), inputs="{}", runner=RunExecution.LOCAL, error_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        run_hosted.assert_not_awaited()
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "request.pipe_unspecified"
        assert problem["params"] == {"candidates": ["say"]}
        assert problem["message"] == f"Bundle '{bundle_path}' does not declare a main_pipe. Specify a pipe code with --pipe."
        assert problem["diagnostics"]["error_class"] == "MethodEntryError"

    def test_the_statistics_record_the_verdict_s_code(
        self, run_hosted: AsyncMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        bundle_path = _write_bundle(directory=tmp_path, source=RefusedBundles.VALIDATION_FAILURE)
        noted = mocker.patch(f"{AGENT_OUTPUT_MODULE}.note_command_error")

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_path), inputs="{}", runner=RunExecution.HOSTED, error_format=CliOutputFormat.JSON)

        capsys.readouterr()
        run_hosted.assert_not_awaited()
        noted.assert_called_once_with(error=UsageStatsError(code="method.invalid", domain=UsageStatsErrorDomain.METHOD))

    def test_a_local_run_keeps_the_operator_s_view(self, run_hosted: AsyncMock, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        """On this machine's runtime the same refusal is a local failure, with the operator's diagnostics and the command's sentence."""
        bundle_path = _write_bundle(directory=tmp_path, source=RefusedBundles.PARSE_FAILURE)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_path), inputs="{}", runner=RunExecution.LOCAL, error_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        run_hosted.assert_not_awaited()
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "method.invalid"
        assert [item["code"] for item in problem["errors"]] == ["method.syntax"]
        assert problem["diagnostics"]["error_class"] == "ValidateBundleError"
        assert problem["message"].startswith(f"Failed to parse bundle '{bundle_path}': ")
