"""Unit tests: `pipelex-agent run … --runner hosted` renders the hosted API's refusal the way it renders a local failure.

The answers are the dev plane's own problem documents, replayed through the real pipelex-sdk `PipelexAPIClient` over
a mocked HTTP transport that answers the version handshake as the hosted API does and refuses the run, so no test
reaches the network.
"""

from __future__ import annotations

import asyncio
import io
import json
from typing import TYPE_CHECKING

import httpx
import pytest
import typer
from pipelex_sdk.client import PipelexAPIClient
from pipelex_sdk.errors import ApiResponseError

from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error_api_response,
    api_response_error_payload,
    set_agent_cli_error_format,
)
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.agent_cli.commands.run.pipe_cmd import run_pipe_cmd
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.error_rendering import (
    HOSTED_REFUSAL_CALLER_NEXT_STEP,
    HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS,
    HOSTED_SERVER_FAULT_NEXT_STEP,
)
from pipelex.hosted.run_config import RunExecution
from tests.unit.pipelex.cli.agent_cli.test_data import RefusalCase, RefusalCases, RefusedRunBodies
from tests.unit.pipelex.hosted.test_data import HostedVersions

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

HOSTED_URL = "https://hosted.test"
RUN_PIPE_MODULE = "pipelex.cli.agent_cli.commands.run.pipe_cmd"
START_ROUTE = ("POST", "/v1/start")


def _answering(*, status: int, body: str, seen: list[httpx.Request], headers: dict[str, str] | None = None) -> httpx.MockTransport:
    """A hosted API that answers its version, then refuses every other request with ``status``, ``body`` and ``headers``."""

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path == "/v1/version":
            return httpx.Response(200, content=HostedVersions.HOSTED.encode("utf-8"), headers={"content-type": "application/json"})
        return httpx.Response(status, content=body.encode("utf-8"), headers={"content-type": "application/problem+json", **(headers or {})})

    return httpx.MockTransport(_handler)


def _install_hosted_api(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, *, status: int, body: str) -> list[httpx.Request]:
    """Point every `PipelexAPIClient` at a mocked hosted API refusing with ``status`` / ``body``; return the requests it receives."""
    monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_test_not_a_secret")
    monkeypatch.setenv(PIPELEX_BASE_URL_ENV_KEY, HOSTED_URL)
    seen: list[httpx.Request] = []
    transport = _answering(status=status, body=body, seen=seen)

    def _start_client(self: PipelexAPIClient) -> PipelexAPIClient:
        self.client = httpx.AsyncClient(transport=transport)
        return self

    mocker.patch.object(PipelexAPIClient, "start_client", _start_client)
    return seen


def _refusal(*, status: int, body: str, headers: dict[str, str] | None = None) -> ApiResponseError:
    """The typed error the real client raises when the hosted API answers `POST /v1/start` this way."""

    async def _start() -> None:
        client = PipelexAPIClient(api_key="plx_sk_test_not_a_secret", base_url=HOSTED_URL)
        client.client = httpx.AsyncClient(transport=_answering(status=status, body=body, seen=[], headers=headers))
        try:
            await client.start(pipe_code="entry", mthds_contents=["# bundle"])
        finally:
            await client.close()

    with pytest.raises(ApiResponseError) as exc_info:
        asyncio.run(_start())
    return exc_info.value


def _routes(*, seen: list[httpx.Request]) -> list[tuple[str, str]]:
    return [(request.method, request.url.path) for request in seen if request.url.path != "/v1/version"]


class TestRunHostedRefusal:
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
        seen = _install_hosted_api(mocker, monkeypatch, status=422, body=case.body)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        assert _routes(seen=seen) == [START_ROUTE]
        start_body = json.loads(seen[-1].content)
        assert start_body["pipe_code"] == "entry"
        assert start_body["mthds_contents"] == ["# bundle\n"]
        captured = capsys.readouterr()
        assert not captured.out
        envelope = json.loads(captured.err)
        assert envelope["error"] is True
        assert envelope["error_type"] == case.error_type
        assert envelope["message"] == f"API POST /v1/start failed (422): {case.reason}"
        assert envelope["hint"] == case.next_step
        assert envelope["error_domain"] == "input"
        assert envelope["http_status"] == 422
        assert envelope["request_id"].startswith("req_")
        assert "retryable" not in envelope
        assert case.failing_pipe in envelope["message"]

    @pytest.mark.usefixtures("tty_stdin")
    def test_run_bundle_json_carries_the_runner_items(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """A refusal at load hands the agent the runner's located items, each with what the runner sent."""
        _install_hosted_api(mocker, monkeypatch, status=422, body=RefusedRunBodies.UNKNOWN_MODEL_AT_LOAD)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, hosted=True)

        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_category"] == "configuration"
        sent_items = json.loads(RefusedRunBodies.UNKNOWN_MODEL_AT_LOAD)["validation_errors"]
        assert len(envelope["validation_errors"]) == len(sent_items)
        for reported, sent in zip(envelope["validation_errors"], sent_items, strict=True):
            assert reported.items() >= sent.items()

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
        _install_hosted_api(mocker, monkeypatch, status=422, body=case.body)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.MARKDOWN, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        captured = capsys.readouterr()
        assert not captured.out
        markdown = captured.err
        assert markdown.startswith(f"# Error: {case.error_type}\n\nAPI POST /v1/start failed (422): {case.reason}\n")
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
        _install_hosted_api(mocker, monkeypatch, status=422, body=RefusedRunBodies.UNKNOWN_MODEL_AT_LOAD)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.MARKDOWN, runner=RunExecution.HOSTED)

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
        _install_hosted_api(mocker, monkeypatch, status=422, body=RefusedRunBodies.UNSERVED_MODEL_AT_RUN)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(
                path=str(bundle_file),
                pipe="entry",
                output_format=CliOutputFormat.MARKDOWN,
                error_format=CliOutputFormat.JSON,
                runner=RunExecution.HOSTED,
            )

        assert json.loads(capsys.readouterr().err)["error_type"] == "ModelNotFoundError"

    @pytest.mark.usefixtures("tty_stdin")
    def test_run_pipe_sends_its_library_and_reports_the_refusal(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """`run pipe` sends the library a local run would load, and answers a refusal with the same envelope."""
        seen = _install_hosted_api(mocker, monkeypatch, status=422, body=RefusedRunBodies.COMBINE_FAILURE_AT_RUN)
        mocker.patch(f"{RUN_PIPE_MODULE}.resolve_pipe_from_exports", return_value=[])

        with pytest.raises(typer.Exit) as exc_info:
            run_pipe_cmd(
                pipe_code="review_topics",
                library_dir=[str(bundle_file.parent)],
                output_format=CliOutputFormat.JSON,
                runner=RunExecution.HOSTED,
            )

        assert exc_info.value.exit_code == 1
        assert json.loads(seen[-1].content)["mthds_contents"] == ["# bundle\n"]
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "StuffFactoryError"
        assert envelope["hint"] == RefusedRunBodies.COMBINE_FAILURE_NEXT_STEP

    @pytest.mark.usefixtures("tty_stdin")
    def test_run_method_by_address_is_resolved_by_the_hosted_api(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A published address goes as `method_ref`, unfetched, and the refusal reads like a local failure."""
        seen = _install_hosted_api(mocker, monkeypatch, status=422, body=RefusedRunBodies.UNSERVED_MODEL_AT_RUN)

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(name="github.com/Pipelex/methods/news@v1.0.0", output_format=CliOutputFormat.MARKDOWN, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        start_body = json.loads(seen[-1].content)
        assert start_body["method_ref"] == "github.com/Pipelex/methods/news@v1.0.0"
        assert "mthds_contents" not in start_body
        markdown = capsys.readouterr().err
        assert markdown.startswith("# Error: ModelNotFoundError\n")
        assert f"> 💡 **Hint:** {RefusedRunBodies.UNSERVED_MODEL_NEXT_STEP}" in markdown

    @pytest.mark.usefixtures("tty_stdin")
    def test_base_url_flag_wins_over_the_environment(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """`--base-url` names the origin every request of the run goes to, over `PIPELEX_BASE_URL`."""
        seen = _install_hosted_api(mocker, monkeypatch, status=422, body=RefusedRunBodies.UNSERVED_MODEL_AT_RUN)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(
                path=str(bundle_file),
                pipe="entry",
                output_format=CliOutputFormat.JSON,
                runner=RunExecution.HOSTED,
                base_url="https://self-hosted.test:8081",
            )

        capsys.readouterr()
        assert seen
        assert {(request.url.host, request.url.port) for request in seen} == {("self-hosted.test", 8081)}

    @pytest.mark.usefixtures("tty_stdin")
    def test_an_unreachable_api_names_the_base_url_settings(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """A hosted API that cannot be reached is a configuration matter: the hint names where the origin comes from."""
        monkeypatch.setenv(PIPELEX_BASE_URL_ENV_KEY, HOSTED_URL)

        def _refuse_connection(request: httpx.Request) -> httpx.Response:
            msg = "connection refused"
            raise httpx.ConnectError(msg, request=request)

        def _start_client(self: PipelexAPIClient) -> PipelexAPIClient:
            self.client = httpx.AsyncClient(transport=httpx.MockTransport(_refuse_connection))
            return self

        mocker.patch.object(PipelexAPIClient, "start_client", _start_client)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "ApiUnreachableError"
        assert envelope["error_domain"] == "config"
        assert PIPELEX_BASE_URL_ENV_KEY in envelope["hint"]

    @pytest.mark.usefixtures("tty_stdin")
    def test_a_server_without_the_run_routes_points_at_the_base_url(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """A server with neither `/v1/start` nor `/v1/execute` is not the hosted API: the hint names where the origin comes from."""
        seen = _install_hosted_api(mocker, monkeypatch, status=404, body='{"detail":"Not Found"}')

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        # The SDK falls back to a blocking execute when the run routes are absent, as a bare runner serves.
        assert _routes(seen=seen) == [START_ROUTE, ("POST", "/v1/execute")]
        envelope = json.loads(capsys.readouterr().err)
        assert envelope["error_type"] == "ApiResponseError"
        assert envelope["http_status"] == 404
        assert envelope["hint"] == HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[404]
        assert "--base-url" in envelope["hint"]

    @pytest.mark.parametrize(
        ("flags", "named"),
        [
            ({"runner": RunExecution.LOCAL, "hosted": True}, "--runner local contradicts --hosted"),
            ({"runner": RunExecution.LOCAL, "base_url": "https://api.pipelex.com"}, "--base-url"),
            ({"hosted": True, "dry_run": True}, "--dry-run"),
            ({"runner": RunExecution.HOSTED, "dry_run": True, "mock_inputs": True}, "--dry-run and --mock-inputs"),
            ({"runner": RunExecution.HOSTED, "base_url": "https://api.pipelex.com/v1"}, "scheme://host[:port]"),
        ],
    )
    @pytest.mark.usefixtures("tty_stdin")
    def test_contradicting_or_local_only_flags_are_refused_before_anything_is_sent(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        flags: dict[str, object],
        named: str,
    ) -> None:
        """Flags naming two places, or a local-only flag on a hosted run, are an argument error, and no request leaves."""
        seen = _install_hosted_api(mocker, monkeypatch, status=500, body="{}")

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, **flags)  # type: ignore[arg-type]

        assert exc_info.value.exit_code == 1
        assert seen == []
        assert named in json.loads(capsys.readouterr().err)["message"]

    def test_payload_of_an_answer_that_is_no_problem_document(self) -> None:
        """A gateway's page gives the client's own class, the server-fault hint, the status, and no runner classification."""
        payload = api_response_error_payload(error=_refusal(status=502, body=RefusedRunBodies.GATEWAY_HTML))

        assert payload["error_type"] == "ApiResponseError"
        assert payload["message"] == f"API POST /v1/start failed (502): {RefusedRunBodies.GATEWAY_HTML}"
        assert payload["hint"] == HOSTED_SERVER_FAULT_NEXT_STEP
        assert payload["http_status"] == 502
        for absent in ("error_domain", "error_category", "retryable", "request_id", "validation_errors", "pipe_code", "pipe_stack"):
            assert absent not in payload

    def test_payload_never_borrows_a_local_hint_or_domain_for_the_runner_class(self) -> None:
        """A runner class with a local hint and retryable flag lends neither to a remote refusal that sent none."""
        body = json.dumps({"detail": "The model is not available", "error_type": "PipeOperatorModelAvailabilityError"})

        payload = api_response_error_payload(error=_refusal(status=500, body=body))

        assert payload["error_type"] == "PipeOperatorModelAvailabilityError"
        assert payload["hint"] == HOSTED_SERVER_FAULT_NEXT_STEP
        assert "retryable" not in payload
        assert "error_domain" not in payload

    def test_payload_carries_the_pipe_members_and_retryable(self) -> None:
        """`pipe_code`, `pipe_stack` and a true `retryable` ride the envelope when the problem carries them."""
        payload = api_response_error_payload(error=_refusal(status=422, body=RefusedRunBodies.LOCATED_WITH_UNKNOWN_ITEM))

        assert payload["pipe_code"] == "analyze_topics"
        assert payload["pipe_stack"] == ["review_topics", "analyze_topics"]
        assert payload["retryable"] is True
        assert payload["hint"] == HOSTED_REFUSAL_CALLER_NEXT_STEP

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

    def test_payload_of_the_platform_rate_limit(self) -> None:
        """A rate limit the runner did not advise on reads as retryable, with its delay, its code and a wait-and-retry hint."""
        payload = api_response_error_payload(error=_refusal(status=429, body=RefusedRunBodies.PLATFORM_RATE_LIMITED, headers={"Retry-After": "12"}))

        assert payload["error_type"] == "ApiResponseError"
        assert payload["hint"] == HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[429]
        assert payload["retryable"] is True
        assert payload["retry_after_seconds"] == 12
        assert payload["error_code"] == "rate_limited"
        assert payload["request_id"] == "req_rate"
        assert "error_domain" not in payload

    def test_payload_of_the_gateway_refusing_a_key(self) -> None:
        """The gateway's bare 403 points at the key, not at a request_id it never sent."""
        payload = api_response_error_payload(error=_refusal(status=403, body=RefusedRunBodies.GATEWAY_FORBIDDEN))

        assert payload["message"] == "API POST /v1/start failed (403): Forbidden"
        assert payload["hint"] == HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[403]
        assert PIPELEX_API_KEY_ENV_KEY in payload["hint"]
        for absent in ("retryable", "request_id", "error_code", "retry_after_seconds"):
            assert absent not in payload

    def test_payload_of_an_unavailable_service_is_never_inferred_retryable(self) -> None:
        """A 503 can follow a run that completed, so only the answer itself can make it retryable."""
        silent = api_response_error_payload(
            error=_refusal(status=503, body=RefusedRunBodies.PLATFORM_RUNNER_UNREACHABLE, headers={"Retry-After": "10"})
        )
        body_saying_yes = json.dumps({**json.loads(RefusedRunBodies.PLATFORM_RUNNER_UNREACHABLE), "retryable": True})
        saying_yes = api_response_error_payload(error=_refusal(status=503, body=body_saying_yes))

        assert "retryable" not in silent
        assert silent["retry_after_seconds"] == 10
        assert silent["error_code"] == "service_unavailable"
        assert silent["hint"] == HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[503]
        assert "repeat a paid run" in silent["hint"]
        assert saying_yes["retryable"] is True

    def test_payload_of_a_refusal_the_caller_must_act_on(self) -> None:
        """A 404 points at the method and the base URL settings, and any other 4xx without a next step asks for a change, not a report."""
        not_found = api_response_error_payload(error=_refusal(status=404, body='{"detail":"No method at that address","code":"method_not_found"}'))
        unprocessable = api_response_error_payload(error=_refusal(status=422, body='{"detail":"Local file paths cannot be used"}'))

        assert not_found["message"] == "API POST /v1/start failed (404): No method at that address"
        assert not_found["hint"] == HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[404]
        assert PIPELEX_BASE_URL_ENV_KEY in not_found["hint"]
        assert unprocessable["hint"] == HOSTED_REFUSAL_CALLER_NEXT_STEP
        for payload in (not_found, unprocessable):
            assert "retryable" not in payload
