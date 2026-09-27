"""Unit tests: `pipelex-agent --runner api run` renders a runner's refusal the way it renders a local failure.

The runner's answers are the dev plane's own problem documents, replayed through the real `MthdsAPIClient`
over a mocked HTTP transport, so no test reaches the network.
"""

from __future__ import annotations

import asyncio
import io
import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import typer
from mthds.runners.api.client import MthdsAPIClient
from mthds.runners.api.exceptions import ApiResponseError
from mthds.runners.types import RunnerType

from pipelex.cli.agent_cli.commands.agent_output import (
    AGENT_ERROR_HINTS,
    CliOutputFormat,
    agent_error_api_response,
    api_response_error_payload,
    set_agent_cli_error_format,
)
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.agent_cli.commands.run.pipe_cmd import run_pipe_cmd
from tests.unit.pipelex.cli.agent_cli.test_data import RefusalCase, RefusalCases, RefusedRunBodies

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

RUNNER_URL = "https://runner.test"
RUN_PIPE_MODULE = "pipelex.cli.agent_cli.commands.run.pipe_cmd"
RUN_METHOD_MODULE = "pipelex.cli.agent_cli.commands.run.method_cmd"


def _answering(*, status: int, body: str, seen: list[httpx.Request]) -> httpx.MockTransport:
    """A transport answering every request with ``status`` and ``body``, recording the requests it saw."""

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, content=body.encode("utf-8"), headers={"content-type": "application/problem+json"})

    return httpx.MockTransport(_handler)


def _install_runner(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, *, status: int, body: str) -> list[httpx.Request]:
    """Point every `MthdsAPIClient` at a mocked runner answering ``status`` / ``body``; return the requests it receives."""
    monkeypatch.setenv("MTHDS_API_KEY", "test-key-not-a-secret")
    monkeypatch.setenv("MTHDS_BASE_URL", RUNNER_URL)
    seen: list[httpx.Request] = []
    transport = _answering(status=status, body=body, seen=seen)

    def _start_client(self: MthdsAPIClient) -> MthdsAPIClient:
        self.client = httpx.AsyncClient(transport=transport)
        return self

    mocker.patch.object(MthdsAPIClient, "start_client", _start_client)
    return seen


def _refusal(*, status: int, body: str) -> ApiResponseError:
    """The typed error the real client raises for this answer."""

    async def _execute() -> None:
        client = MthdsAPIClient(api_key="test-key-not-a-secret", base_url=RUNNER_URL)
        client.client = httpx.AsyncClient(transport=_answering(status=status, body=body, seen=[]))
        try:
            await client.execute(pipe_code="entry", mthds_contents=["# bundle"])
        finally:
            await client.close()

    with pytest.raises(ApiResponseError) as exc_info:
        asyncio.run(_execute())
    return exc_info.value


def _api_ctx(mocker: MockerFixture) -> Any:
    ctx = mocker.MagicMock()
    ctx.obj = {"runner": RunnerType.API}
    return ctx


class TestRunApiRefusal:
    @pytest.fixture
    def tty_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Make stdin look like a TTY so parse_cli_inputs skips the stdin fallback."""
        mock_stdin = io.StringIO("")
        mock_stdin.isatty = lambda: True  # type: ignore[assignment]
        monkeypatch.setattr("sys.stdin", mock_stdin)

    @pytest.fixture
    def bundle_file(self, tmp_path: Path) -> Path:
        """A bundle file the command reads and sends as is (never parsed: --pipe is passed)."""
        path = tmp_path / "bundle.mthds"
        path.write_text("# bundle\n", encoding="utf-8")
        return path

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize("case", RefusalCases.DEV_PLANE, ids=[case.topic for case in RefusalCases.DEV_PLANE])
    def test_run_bundle_json_carries_the_reason_the_pipe_and_the_next_step(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        case: RefusalCase,
    ) -> None:
        """The JSON envelope of each dev-plane refusal names its class, its located reason, its next step and its domain."""
        seen = _install_runner(mocker, monkeypatch, status=422, body=case.body)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(ctx=_api_ctx(mocker), path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        assert [(request.method, request.url.path) for request in seen] == [("POST", "/v1/execute")]
        captured = capsys.readouterr()
        assert not captured.out
        envelope = json.loads(captured.err)
        assert envelope["error"] is True
        assert envelope["error_type"] == case.error_type
        assert envelope["message"] == f"API POST /v1/execute failed (422): {case.reason}"
        assert envelope["hint"] == case.next_step
        assert envelope["error_domain"] == "input"
        assert envelope["http_status"] == 422
        assert envelope["request_id"].startswith("req_")
        assert "retryable" not in envelope
        assert case.failing_pipe in envelope["message"]

    @pytest.mark.usefixtures("tty_stdin")
    def test_run_bundle_json_carries_the_runner_items_whole(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """A refusal at load hands the agent the runner's located items exactly as the runner sent them."""
        _install_runner(mocker, monkeypatch, status=422, body=RefusedRunBodies.UNKNOWN_MODEL_AT_LOAD)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(ctx=_api_ctx(mocker), path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON)

        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_category"] == "configuration"
        assert envelope["validation_errors"] == json.loads(RefusedRunBodies.UNKNOWN_MODEL_AT_LOAD)["validation_errors"]

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize("case", RefusalCases.DEV_PLANE, ids=[case.topic for case in RefusalCases.DEV_PLANE])
    def test_run_bundle_markdown_names_the_reason_the_pipe_and_the_next_step(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        case: RefusalCase,
    ) -> None:
        """The markdown of each dev-plane refusal reads like a local failure: heading, reason, hint, details."""
        _install_runner(mocker, monkeypatch, status=422, body=case.body)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(ctx=_api_ctx(mocker), path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.MARKDOWN)

        assert exc_info.value.exit_code == 1
        captured = capsys.readouterr()
        assert not captured.out
        markdown = captured.err
        assert markdown.startswith(f"# Error: {case.error_type}\n\nAPI POST /v1/execute failed (422): {case.reason}\n")
        assert f"> 💡 **Hint:** {case.next_step}" in markdown
        assert "Next step:" not in markdown
        assert "- **error_domain:** input" in markdown
        assert "- **http_status:** 422" in markdown
        assert case.failing_pipe in markdown
        assert "error_source" not in markdown

    @pytest.mark.usefixtures("tty_stdin")
    def test_run_bundle_markdown_renders_the_runner_items_as_validate_does(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """The runner's items render as the grouped prose `validate` prints, not as a JSON dump."""
        _install_runner(mocker, monkeypatch, status=422, body=RefusedRunBodies.UNKNOWN_MODEL_AT_LOAD)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(ctx=_api_ctx(mocker), path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.MARKDOWN)

        markdown = capsys.readouterr().err
        assert "## Pipe validation errors" in markdown
        assert "Pipe: `draft_pitch`" in markdown
        assert "Field: `model`" in markdown
        assert "validation_errors" not in markdown

    @pytest.mark.usefixtures("tty_stdin")
    def test_run_bundle_error_format_json_overrides_markdown_format(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """`--error-format json` gives the JSON envelope even when the success format is markdown."""
        _install_runner(mocker, monkeypatch, status=422, body=RefusedRunBodies.UNSERVED_MODEL_AT_RUN)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(
                ctx=_api_ctx(mocker),
                path=str(bundle_file),
                pipe="entry",
                output_format=CliOutputFormat.MARKDOWN,
                error_format=CliOutputFormat.JSON,
            )

        assert json.loads(capsys.readouterr().err)["error_type"] == "ModelNotFoundError"

    @pytest.mark.usefixtures("tty_stdin")
    def test_run_pipe_reports_the_refusal(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        """`run pipe` on the API runner answers a refusal with the same envelope."""
        _install_runner(mocker, monkeypatch, status=422, body=RefusedRunBodies.COMBINE_FAILURE_AT_RUN)
        mocker.patch(f"{RUN_PIPE_MODULE}.resolve_pipe_from_exports", return_value=[])

        with pytest.raises(typer.Exit) as exc_info:
            run_pipe_cmd(ctx=_api_ctx(mocker), pipe_code="review_topics", output_format=CliOutputFormat.JSON)

        assert exc_info.value.exit_code == 1
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "StuffFactoryError"
        assert envelope["hint"] == RefusedRunBodies.COMBINE_FAILURE_NEXT_STEP

    @pytest.mark.usefixtures("tty_stdin")
    def test_run_method_reports_the_refusal(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """`run method` on the API runner answers a refusal with the same markdown."""
        _install_runner(mocker, monkeypatch, status=422, body=RefusedRunBodies.UNSERVED_MODEL_AT_RUN)
        method_mock = mocker.MagicMock()
        method_mock.mthds_files = [bundle_file]
        method_mock.path = bundle_file.parent
        method_mock.provenance = None
        mocker.patch(f"{RUN_METHOD_MODULE}.resolve_method_target", return_value=("digest_article", [str(bundle_file.parent)], method_mock))

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(ctx=_api_ctx(mocker), name="news-digest", output_format=CliOutputFormat.MARKDOWN)

        assert exc_info.value.exit_code == 1
        markdown = capsys.readouterr().err
        assert markdown.startswith("# Error: ModelNotFoundError\n")
        assert f"> 💡 **Hint:** {RefusedRunBodies.UNSERVED_MODEL_NEXT_STEP}" in markdown

    def test_payload_of_an_answer_that_is_no_problem_document(self) -> None:
        """A gateway's page gives the client's own class, the static hint, the status, and no runner classification."""
        payload = api_response_error_payload(error=_refusal(status=502, body=RefusedRunBodies.GATEWAY_HTML))

        assert payload["error_type"] == "ApiResponseError"
        assert payload["message"] == f"API POST /v1/execute failed (502): {RefusedRunBodies.GATEWAY_HTML}"
        assert payload["hint"] == AGENT_ERROR_HINTS["ApiResponseError"]
        assert payload["http_status"] == 502
        for absent in ("error_domain", "error_category", "retryable", "request_id", "validation_errors", "pipe_code", "pipe_stack"):
            assert absent not in payload

    def test_payload_never_borrows_a_local_hint_or_domain_for_the_runner_class(self) -> None:
        """A runner class with a local hint and retryable flag lends neither to a remote refusal that sent none."""
        body = json.dumps({"detail": "The model is not available", "error_type": "PipeOperatorModelAvailabilityError"})

        payload = api_response_error_payload(error=_refusal(status=500, body=body))

        assert payload["error_type"] == "PipeOperatorModelAvailabilityError"
        assert payload["hint"] == AGENT_ERROR_HINTS["ApiResponseError"]
        assert "retryable" not in payload
        assert "error_domain" not in payload

    def test_payload_carries_the_pipe_members_and_retryable(self) -> None:
        """`pipe_code`, `pipe_stack` and a true `retryable` ride the envelope when the problem carries them."""
        payload = api_response_error_payload(error=_refusal(status=422, body=RefusedRunBodies.LOCATED_WITH_UNKNOWN_ITEM))

        assert payload["pipe_code"] == "analyze_topics"
        assert payload["pipe_stack"] == ["review_topics", "analyze_topics"]
        assert payload["retryable"] is True
        assert payload["hint"] == AGENT_ERROR_HINTS["ApiResponseError"]

    def test_markdown_keeps_an_item_this_version_cannot_type(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An item from a newer runner stays readable as JSON under Details rather than failing the rendering."""
        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)

        with pytest.raises(typer.Exit):
            agent_error_api_response(error=_refusal(status=422, body=RefusedRunBodies.LOCATED_WITH_UNKNOWN_ITEM))

        markdown = capsys.readouterr().err
        assert markdown.startswith("# Error: StuffFactoryError\n")
        assert "- **validation_errors:**" in markdown
        assert '"error_type": "some_future_fault"' in markdown
        assert "- **pipe_code:** analyze_topics" in markdown
        assert '"review_topics",' in markdown
