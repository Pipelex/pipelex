"""Unit tests: `pipelex-agent run … --runner hosted` reports a refused, failed or unreachable run as the problem it got.

The answers are a runner's own problem documents, replayed through the real pipelex-sdk `PipelexAPIClient` over a mocked
HTTP transport that answers the version handshake as the hosted API does and refuses the run, or refuses every
connection, so no test reaches the network.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import typer
from pipelex_sdk.client import PipelexAPIClient

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.run.bundle_cmd import run_bundle_cmd
from pipelex.cli.agent_cli.commands.run.method_cmd import run_method_cmd
from pipelex.cli.agent_cli.commands.run.pipe_cmd import run_pipe_cmd
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY, PIPELEX_BASE_URL_ENV_KEY
from pipelex.hosted.error_rendering import (
    HOSTED_FORBIDDEN_NEXT_STEP,
    HOSTED_MISSING_KEY_NEXT_STEP,
    HOSTED_REFUSAL_CALLER_NEXT_STEP,
    HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS,
    HOSTED_UNREACHABLE_NEXT_STEP,
)
from pipelex.hosted.run_config import RunExecution
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsError, UsageStatsErrorDomain
from tests.unit.pipelex.cli.agent_cli.test_data import (
    GatewayAnswers,
    HostedMethodItems,
    HostedPlaneRefusals,
    OperatorViewAnswers,
    RetiredEnvelope,
    RunnerOwnMethodRefusals,
    RunnerOwnRefusals,
    RunnerProblems,
    UndeclaredMembers,
)
from tests.unit.pipelex.hosted.test_data import HostedVersions

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

HOSTED_URL = "https://hosted.test"
RUN_PIPE_MODULE = "pipelex.cli.agent_cli.commands.run.pipe_cmd"
START_ROUTE = ("POST", "/v1/start")
#: The request id a hosted API names in its `X-Request-ID` header.
HEADER_REQUEST_ID = "01M55PHEADER000000000000000"
#: The problem pipelex-sdk decides for a runner that cannot be reached at `HOSTED_URL`, the base client's own, with the
#: next step the human CLI gives it.
UNREACHABLE_PROBLEM: dict[str, Any] = {
    "type": "https://mthds.ai/errors/client.unreachable",
    "title": "The runtime could not be reached",
    "detail": f"The client could not connect to the runtime at {HOSTED_URL}.",
    "code": "client.unreachable",
    "domain": "runtime",
    "retry": "yes",
    "next_step": {"kind": "retry", "detail": HOSTED_UNREACHABLE_NEXT_STEP},
    "params": {"base_url": HOSTED_URL},
}
#: A runner's own problem for a fault it met while running, which an answer on the run request cannot be trusted for.
RUNNER_FAULT: str = json.dumps(
    {
        "type": "https://mthds.ai/errors/runtime.unexpected",
        "title": "The runtime met an unexpected error",
        "status": 500,
        "detail": "The runtime met an unexpected error.",
        "code": "runtime.unexpected",
        "domain": "runtime",
        "retry": "no",
        "next_step": {"kind": "report", "detail": "Report this to whoever runs the runtime."},
    }
)


def _answering(
    *, status: int, body: str, seen: list[httpx.Request], headers: dict[str, str] | None = None, version: str = HostedVersions.HOSTED
) -> httpx.MockTransport:
    """A runner that answers its ``version``, then refuses every other request with ``status``, ``body`` and ``headers``."""

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path == "/v1/version":
            return httpx.Response(200, content=version.encode("utf-8"), headers={"content-type": "application/json"})
        answer_headers = {"content-type": "application/problem+json", **(headers or {})}
        return httpx.Response(status, content=body.encode("utf-8"), headers=answer_headers)

    return httpx.MockTransport(_handler)


def _refusing_connections(request: httpx.Request) -> httpx.Response:
    """A host where nothing listens: every connection is refused."""
    msg = "connection refused"
    raise httpx.ConnectError(msg, request=request)


def _install_transport(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, *, transport: httpx.MockTransport) -> None:
    """Point every `PipelexAPIClient` at ``transport``, with a key and `HOSTED_URL` as the origin."""
    monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "plx_sk_test_not_a_secret")
    monkeypatch.setenv(PIPELEX_BASE_URL_ENV_KEY, HOSTED_URL)

    def _start_client(self: PipelexAPIClient) -> PipelexAPIClient:
        self.client = httpx.AsyncClient(transport=transport)
        return self

    mocker.patch.object(PipelexAPIClient, "start_client", _start_client)


def _install_hosted_api(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: int,
    body: str,
    headers: dict[str, str] | None = None,
    version: str = HostedVersions.HOSTED,
) -> list[httpx.Request]:
    """Point every `PipelexAPIClient` at a mocked runner refusing with ``status`` / ``body``; return the requests it receives.

    The runner answers its version as the hosted API does unless ``version`` says otherwise.
    """
    seen: list[httpx.Request] = []
    _install_transport(mocker, monkeypatch, transport=_answering(status=status, body=body, seen=seen, headers=headers, version=version))
    return seen


def _install_unreachable_api(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every `PipelexAPIClient` at `HOSTED_URL`, where nothing listens."""
    _install_transport(mocker, monkeypatch, transport=httpx.MockTransport(_refusing_connections))


def _routes(*, seen: list[httpx.Request]) -> list[tuple[str, str]]:
    return [(request.method, request.url.path) for request in seen if request.url.path != "/v1/version"]


def _assert_no_retired_member(*, problem: dict[str, Any]) -> None:
    """No member of the envelope this CLI wrote before it reported problems is left in a reported problem."""
    for retired in RetiredEnvelope.MEMBERS:
        assert retired not in problem, retired


def _assert_no_retired_markdown(*, markdown: str) -> None:
    """The Markdown is the problem's: no heading, callout or member of the retired envelope, and no class name."""
    for retired in ("# Error:", "**Hint:**", "error_type", "error_source", "error_domain", "ApiResponseError", "ApiUnreachableError"):
        assert retired not in markdown, retired


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
    @pytest.mark.parametrize(
        "body",
        [
            RunnerProblems.INPUT_MISSING,
            RunnerProblems.OUTPUT_MULTIPLICITY,
            RunnerProblems.UNKNOWN_MODEL_AT_LOAD,
            RunnerProblems.ITEMS_WITH_SUGGESTIONS,
        ],
        ids=["input_missing", "output_multiplicity", "unknown_model_at_load", "items_with_suggestions"],
    )
    def test_json_is_the_runner_s_problem_as_it_came(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path, body: str
    ) -> None:
        """A refused run reaches the error stream as the problem the runner answered, member for member, its items included."""
        seen = _install_hosted_api(mocker, monkeypatch, status=422, body=body)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        assert _routes(seen=seen) == [START_ROUTE]
        start_body = json.loads(seen[-1].content)
        assert start_body["pipe_code"] == "entry"
        assert start_body["mthds_contents"] == ["# bundle\n"]
        captured = capsys.readouterr()
        assert not captured.out
        problem = json.loads(captured.err)
        assert problem == json.loads(body)
        _assert_no_retired_member(problem=problem)

    @pytest.mark.usefixtures("tty_stdin")
    def test_markdown_reads_the_runner_s_problem(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """The default Markdown renders the runner's problem as a local failure's: title, detail, next step, code, request, location."""
        _install_hosted_api(mocker, monkeypatch, status=422, body=RunnerProblems.INPUT_MISSING)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        captured = capsys.readouterr()
        assert not captured.out
        markdown = captured.err
        assert markdown.startswith("## A required input is missing\n\nThe request does not give the input 'topic', which the method requires.\n")
        assert "**Next step** (`change_input`): Add the input 'topic' to the request, then send it again." in markdown
        assert "- Code: `input.missing` (domain input, retry no)" in markdown
        assert "- Request id: `01M55P3J09ADGMD2MW5FSN6S1P`" in markdown
        assert "- Location: pipe 'write_slogan', path write_slogan" in markdown
        _assert_no_retired_markdown(markdown=markdown)

    @pytest.mark.usefixtures("tty_stdin")
    def test_markdown_lists_the_runner_s_items_with_their_suggestions_and_fix(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """The runner's items read one per line, with code, sentence, location, suggestions and fix, never as `validate`'s former prose."""
        _install_hosted_api(mocker, monkeypatch, status=422, body=RunnerProblems.ITEMS_WITH_SUGGESTIONS)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.MARKDOWN, runner=RunExecution.HOSTED)

        markdown = capsys.readouterr().err
        assert (
            "### Errors\n\n"
            "- `model.unknown`: The method names the llm model 'gpt-5.1', which no catalog knows. (pipe 'draft_pitch', field 'model')\n"
            "  - Suggestions: `gpt-5.5`, `gpt-5.4`\n"
            "  - Suggested fix (`rename-model`, unsafe, confirm before applying): Replace model 'gpt-5.1' of pipe 'draft_pitch' with 'gpt-5.5'"
        ) in markdown
        assert "## Pipe validation errors" not in markdown
        _assert_no_retired_markdown(markdown=markdown)

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize(
        ("status", "body"),
        [(502, GatewayAnswers.HTML_PAGE), (500, RUNNER_FAULT)],
        ids=["gateway_page", "runner_problem"],
    )
    def test_a_server_fault_on_the_run_request_leaves_the_outcome_unknown(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        status: int,
        body: str,
    ) -> None:
        """A 5xx on the run request may follow a run that started, so it is the client's `client.outcome_unknown`, whatever its body."""
        _install_hosted_api(mocker, monkeypatch, status=status, body=body)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "client.outcome_unknown"
        assert problem["domain"] == "runtime"
        assert problem["retry"] == "outcome_unknown"
        assert problem["next_step"]["kind"] == "read_run"
        _assert_no_retired_member(problem=problem)

    @pytest.mark.usefixtures("tty_stdin")
    def test_a_server_fault_in_markdown(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        _install_hosted_api(mocker, monkeypatch, status=502, body=GatewayAnswers.HTML_PAGE)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", runner=RunExecution.HOSTED)

        markdown = capsys.readouterr().err
        assert markdown.startswith("## The call may have created a run\n")
        assert "- Code: `client.outcome_unknown` (domain runtime, retry outcome_unknown)" in markdown
        assert "502 Bad Gateway" not in markdown
        _assert_no_retired_markdown(markdown=markdown)

    @pytest.mark.usefixtures("tty_stdin")
    def test_an_unreachable_runner_is_the_client_s_client_unreachable(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """A runner nothing answers for is the base client's `client.unreachable`, naming the base URL, with no class name."""
        _install_unreachable_api(mocker, monkeypatch)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        assert json.loads(capsys.readouterr().err) == UNREACHABLE_PROBLEM

    @pytest.mark.usefixtures("tty_stdin")
    def test_an_unreachable_runner_in_markdown(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        _install_unreachable_api(mocker, monkeypatch)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.MARKDOWN, runner=RunExecution.HOSTED)

        markdown = capsys.readouterr().err
        assert markdown.startswith(f"## The runtime could not be reached\n\nThe client could not connect to the runtime at {HOSTED_URL}.\n")
        assert f"**Next step** (`retry`): {HOSTED_UNREACHABLE_NEXT_STEP}" in markdown
        assert "- Code: `client.unreachable` (domain runtime, retry yes)" in markdown
        assert "ConnectError" not in markdown
        _assert_no_retired_markdown(markdown=markdown)

    @pytest.mark.usefixtures("tty_stdin")
    def test_error_format_json_overrides_markdown_format(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """`--error-format json` gives the JSON problem even when the success format is markdown."""
        _install_hosted_api(mocker, monkeypatch, status=422, body=RunnerProblems.UNKNOWN_MODEL_AT_LOAD)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(
                path=str(bundle_file),
                pipe="entry",
                output_format=CliOutputFormat.MARKDOWN,
                error_format=CliOutputFormat.JSON,
                runner=RunExecution.HOSTED,
            )

        assert json.loads(capsys.readouterr().err) == json.loads(RunnerProblems.UNKNOWN_MODEL_AT_LOAD)

    @pytest.mark.usefixtures("tty_stdin")
    def test_run_pipe_sends_its_library_and_reports_the_refusal(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """`run pipe` sends the library a local run would load, and reports a refusal as the runner's problem."""
        seen = _install_hosted_api(mocker, monkeypatch, status=422, body=RunnerProblems.OUTPUT_MULTIPLICITY)
        mocker.patch(f"{RUN_PIPE_MODULE}.resolve_pipe_from_exports", return_value=[])

        with pytest.raises(typer.Exit) as exc_info:
            run_pipe_cmd(
                pipe_code="review_topic",
                library_dir=[str(bundle_file.parent)],
                output_format=CliOutputFormat.JSON,
                runner=RunExecution.HOSTED,
            )

        assert exc_info.value.exit_code == 1
        assert json.loads(seen[-1].content)["mthds_contents"] == ["# bundle\n"]
        assert json.loads(capsys.readouterr().err) == json.loads(RunnerProblems.OUTPUT_MULTIPLICITY)

    @pytest.mark.usefixtures("tty_stdin")
    def test_run_method_by_address_is_resolved_by_the_hosted_api(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A published address goes as `method_ref`, unfetched, and the refusal reads as the runner's problem."""
        seen = _install_hosted_api(mocker, monkeypatch, status=422, body=RunnerProblems.UNKNOWN_MODEL_AT_LOAD)

        with pytest.raises(typer.Exit) as exc_info:
            run_method_cmd(name="github.com/Pipelex/methods/news@v1.0.0", output_format=CliOutputFormat.MARKDOWN, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        start_body = json.loads(seen[-1].content)
        assert start_body["method_ref"] == "github.com/Pipelex/methods/news@v1.0.0"
        assert "mthds_contents" not in start_body
        markdown = capsys.readouterr().err
        assert markdown.startswith("## The method does not validate\n")
        assert (
            "- `model.unknown`: The method names the llm model 'claude-4.5-haiku', which no catalog knows. (pipe 'write_slogan', field 'model')"
            in (markdown)
        )

    @pytest.mark.usefixtures("tty_stdin")
    def test_base_url_flag_wins_over_the_environment(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """`--base-url` names the origin every request of the run goes to, over `PIPELEX_BASE_URL`."""
        seen = _install_hosted_api(mocker, monkeypatch, status=422, body=RunnerProblems.INPUT_MISSING)

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
    def test_a_server_without_the_run_routes_serves_no_such_route(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """A server with neither `/v1/start` nor `/v1/execute` answers a bare 404: `request.not_found`, telling to check the origin."""
        seen = _install_hosted_api(mocker, monkeypatch, status=404, body=GatewayAnswers.NOT_FOUND)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        # The SDK falls back to a blocking execute when the run routes are absent, as a bare runner serves.
        assert _routes(seen=seen) == [START_ROUTE, ("POST", "/v1/execute")]
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "request.not_found"
        assert problem["detail"] == "Not Found"
        assert problem["next_step"] == {"kind": "upgrade", "detail": HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[404]}
        _assert_no_retired_member(problem=problem)

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize(
        ("status", "body", "headers", "expected"),
        [
            (
                401,
                HostedPlaneRefusals.UNAUTHORIZED,
                {},
                {
                    "type": "https://mthds.ai/errors/auth.invalid_credential",
                    "title": "The credential was refused",
                    "status": 401,
                    "detail": "The API key is not valid.",
                    "code": "auth.invalid_credential",
                    "domain": "account",
                    "retry": "no",
                    "next_step": {"kind": "check_credentials", "detail": HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[401]},
                    "request_id": "01M55PLEGACY401000000000000",
                },
            ),
            (
                403,
                HostedPlaneRefusals.FORBIDDEN,
                {},
                {
                    "type": "https://mthds.ai/errors/auth.forbidden",
                    "title": "The credential does not permit this",
                    "status": 403,
                    "detail": "Your role in this organization does not allow running methods.",
                    "code": "auth.forbidden",
                    "domain": "account",
                    "retry": "no",
                    "next_step": {"kind": "request_access", "detail": HOSTED_FORBIDDEN_NEXT_STEP},
                    "request_id": "01M55PLEGACY403000000000000",
                },
            ),
            (
                403,
                HostedPlaneRefusals.FORBIDDEN_OPERATION,
                {},
                {
                    "type": "https://mthds.ai/errors/auth.forbidden",
                    "title": "The credential does not permit this",
                    "status": 403,
                    "detail": "This route is served to a web session only.",
                    "code": "auth.forbidden",
                    "domain": "account",
                    "retry": "no",
                    "next_step": {"kind": "request_access", "detail": HOSTED_FORBIDDEN_NEXT_STEP},
                },
            ),
            (
                403,
                HostedPlaneRefusals.FORBIDDEN_EXPIRED_KEY,
                {},
                {
                    "type": "https://mthds.ai/errors/auth.invalid_credential",
                    "title": "The credential was refused",
                    "status": 403,
                    "detail": "The API key has expired.",
                    "code": "auth.invalid_credential",
                    "domain": "account",
                    "retry": "no",
                    "next_step": {"kind": "check_credentials", "detail": HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[403]},
                },
            ),
            (
                403,
                GatewayAnswers.FORBIDDEN,
                {"x-request-id": HEADER_REQUEST_ID},
                {
                    "type": "https://mthds.ai/errors/auth.invalid_credential",
                    "title": "The credential was refused",
                    "status": 403,
                    "detail": "Forbidden",
                    "code": "auth.invalid_credential",
                    "domain": "account",
                    "retry": "no",
                    "next_step": {"kind": "check_credentials", "detail": HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[403]},
                    "request_id": HEADER_REQUEST_ID,
                },
            ),
            (
                404,
                HostedPlaneRefusals.RUN_NOT_FOUND,
                {},
                {
                    "type": "https://mthds.ai/errors/run.not_found",
                    "title": "No such run",
                    "status": 404,
                    "detail": "No run run_9 is visible to this key.",
                    "code": "run.not_found",
                    "domain": "input",
                    "retry": "no",
                    "next_step": {"kind": "change_input", "detail": "Check the run id, then read the run again."},
                },
            ),
            (
                404,
                HostedPlaneRefusals.METHOD_VERSION_NOT_FOUND,
                {},
                {
                    "type": "https://mthds.ai/errors/method.not_found",
                    "title": "No method at this address",
                    "status": 404,
                    "detail": "The method mt_7 has no published version 3.",
                    "code": "method.not_found",
                    "domain": "input",
                    "retry": "no",
                    "next_step": {"kind": "change_input", "detail": HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[404]},
                },
            ),
            (
                429,
                HostedPlaneRefusals.RATE_LIMITED,
                {"retry-after": "30"},
                {
                    "type": "https://mthds.ai/errors/account.rate_limited",
                    "title": "The account is over its request rate",
                    "status": 429,
                    "detail": "Too many runs started in the last minute.",
                    "code": "account.rate_limited",
                    "domain": "account",
                    "retry": "yes",
                    "retry_after": 30,
                    "next_step": {"kind": "wait", "detail": HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[429]},
                    "request_id": "01M55PLEGACY429000000000000",
                },
            ),
            (
                429,
                HostedPlaneRefusals.RATE_LIMITED_BODY_DELAY,
                {},
                {
                    "type": "https://mthds.ai/errors/account.rate_limited",
                    "title": "The account is over its request rate",
                    "status": 429,
                    "detail": "Too many runs started in the last minute.",
                    "code": "account.rate_limited",
                    "domain": "account",
                    "retry": "yes",
                    "retry_after": 12,
                    "next_step": {"kind": "wait", "detail": HOSTED_REFUSAL_NEXT_STEPS_BY_STATUS[429]},
                },
            ),
        ],
        ids=[
            "unauthorized",
            "forbidden",
            "forbidden_operation",
            "forbidden_expired_key",
            "gateway_forbidden",
            "run_not_found",
            "method_version_not_found",
            "rate_limited",
            "rate_limited_body_delay",
        ],
    )
    def test_a_refusal_of_the_hosted_plane_reads_as_its_core_code_with_the_hosted_guidance(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        status: int,
        body: str,
        headers: dict[str, str],
        expected: dict[str, Any],
    ) -> None:
        """The hosted plane answers in its pre-standard shape: its refusal reads as the core code its status and its own
        code name, the plane's own detail kept, the next step the human CLI gives, and a rate limit's delay from its header
        or its body. A 403 the platform answers with an authorization code refuses a key it authenticated; one with any
        other code, and the edge's bare 403, may refuse the key itself.
        """
        _install_hosted_api(mocker, monkeypatch, status=status, body=body, headers=headers)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        problem = json.loads(capsys.readouterr().err)
        assert problem == expected
        _assert_no_retired_member(problem=problem)

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize(
        ("status", "body", "detail"),
        [(401, HostedPlaneRefusals.UNAUTHORIZED, "The API key is not valid."), (403, GatewayAnswers.FORBIDDEN, "Forbidden")],
        ids=["unauthorized", "gateway_forbidden"],
    )
    def test_a_refused_request_that_carried_no_key_is_a_missing_credential(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        status: int,
        body: str,
        detail: str,
    ) -> None:
        """With no key sent, a refused credential is a missing one, and its next step says how to get a key, never that one was refused."""
        _install_hosted_api(mocker, monkeypatch, status=status, body=body)
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "")

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.MARKDOWN, runner=RunExecution.HOSTED)

        markdown = capsys.readouterr().err
        assert markdown.startswith(f"## No credential was sent\n\n{detail}\n")
        assert f"**Next step** (`check_credentials`): {HOSTED_MISSING_KEY_NEXT_STEP}" in markdown
        assert "refused the credentials" not in markdown
        assert "- Code: `auth.missing_credential` (domain account, retry no)" in markdown
        _assert_no_retired_markdown(markdown=markdown)

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize("error_format", [CliOutputFormat.JSON, CliOutputFormat.MARKDOWN])
    def test_a_runner_s_own_refusal_in_the_former_shape_keeps_its_reason(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        error_format: CliOutputFormat,
    ) -> None:
        """A runner's own 422, which no standard client reads, keeps the client's `client.response_unreadable` but tells
        its reason and the step the human CLI gives it, never to report a body this CLI does not print.
        """
        _install_hosted_api(mocker, monkeypatch, status=422, body=RunnerOwnRefusals.RESERVED_OBJECT_KEY)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=error_format, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        printed = capsys.readouterr().err
        reason = json.loads(RunnerOwnRefusals.RESERVED_OBJECT_KEY)["detail"]
        match error_format:
            case CliOutputFormat.JSON:
                problem = json.loads(printed)
                assert problem == {
                    "type": "https://mthds.ai/errors/client.response_unreadable",
                    "title": "The runtime's answer could not be read",
                    "status": 422,
                    "detail": reason,
                    "code": "client.response_unreadable",
                    "domain": "runtime",
                    "retry": "no",
                    "next_step": {"kind": "change_input", "detail": HOSTED_REFUSAL_CALLER_NEXT_STEP},
                    "params": {"status": 422},
                    "request_id": "01M55PRESERVED00000000000",
                }
                _assert_no_retired_member(problem=problem)
            case CliOutputFormat.MARKDOWN:
                assert printed.startswith(f"## The runtime's answer could not be read\n\n{reason}\n")
                assert f"**Next step** (`change_input`): {HOSTED_REFUSAL_CALLER_NEXT_STEP}" in printed
                assert "with the status and the body" not in printed
                _assert_no_retired_markdown(markdown=printed)

    @pytest.mark.usefixtures("tty_stdin")
    def test_a_refusal_in_the_former_shape_takes_the_step_kind_its_advice_names(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
    ) -> None:
        """A 4xx in the former shape that advises a step of its own kind, here checking the billing, reports that kind
        beside the advice it gave, never `change_input`, so the step's kind and its detail agree.
        """
        _install_hosted_api(mocker, monkeypatch, status=402, body=RunnerOwnRefusals.NO_CREDIT)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "client.response_unreadable"
        assert problem["status"] == 402
        assert problem["detail"] == RunnerOwnRefusals.NO_CREDIT_REASON
        assert problem["next_step"] == {"kind": "check_account", "detail": RunnerOwnRefusals.NO_CREDIT_ADVICE}
        _assert_no_retired_member(problem=problem)

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize("error_format", [CliOutputFormat.JSON, CliOutputFormat.MARKDOWN])
    @pytest.mark.parametrize(
        ("version", "route"),
        [(HostedVersions.HOSTED, START_ROUTE), (HostedVersions.BARE_RUNNER, ("POST", "/v1/execute"))],
        ids=["start", "execute"],
    )
    def test_a_runner_s_own_refusal_of_a_method_in_the_former_shape_lists_its_items(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        version: str,
        route: tuple[str, str],
        error_format: CliOutputFormat,
    ) -> None:
        """A runner's own 422 in the former shape that lists validation items is `method.invalid`, its items coded as a
        local verdict codes them, with its reason as the detail and its advice as the next step, as a stored report in the
        same shape reads, so the agent CLI lists what the human CLI lists.
        """
        seen = _install_hosted_api(mocker, monkeypatch, status=422, body=RunnerOwnMethodRefusals.INVALID_METHOD, version=version)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=error_format, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        assert _routes(seen=seen) == [route]
        printed = capsys.readouterr().err
        match error_format:
            case CliOutputFormat.JSON:
                problem = json.loads(printed)
                assert problem == {
                    "type": "https://mthds.ai/errors/method.invalid",
                    "title": "The method does not validate",
                    "status": 422,
                    "detail": RunnerOwnMethodRefusals.REASON,
                    "code": "method.invalid",
                    "domain": "method",
                    "retry": "no",
                    "next_step": {"kind": "change_model", "detail": RunnerOwnMethodRefusals.ADVICE},
                    "errors": HostedMethodItems.PROBLEM_ITEMS[:2],
                    "request_id": "01M55PINVALIDMETHOD000000",
                }
                _assert_no_retired_member(problem=problem)
            case CliOutputFormat.MARKDOWN:
                assert printed.startswith(f"## The method does not validate\n\n{RunnerOwnMethodRefusals.REASON}\n")
                assert f"**Next step** (`change_model`): {RunnerOwnMethodRefusals.ADVICE}" in printed
                assert "### Errors" in printed
                assert (
                    f"- `model.unknown`: {HostedMethodItems.PROBLEM_ITEMS[1]['detail']} (pipe 'draft', field 'model', file 'main.mthds')" in printed
                )
                assert "client.response_unreadable" not in printed
                _assert_no_retired_markdown(markdown=printed)

    @pytest.mark.usefixtures("tty_stdin")
    def test_a_runner_s_problem_is_reported_by_its_declared_members_alone(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """Members neither the standard nor Pipelex declares, at any level, are left out: the retired envelope does not come back."""
        _install_hosted_api(mocker, monkeypatch, status=422, body=UndeclaredMembers.SENT)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        problem = json.loads(capsys.readouterr().err)
        assert problem == UndeclaredMembers.REPORTED
        _assert_no_retired_member(problem=problem)

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize(
        ("body", "request_id"),
        [
            (OperatorViewAnswers.UNREADABLE_REQUEST_ID, HEADER_REQUEST_ID),
            (OperatorViewAnswers.UNREADABLE_DIAGNOSTICS, "01M55PREQUEST0000000000000"),
        ],
        ids=["unreadable_request_id", "unreadable_diagnostics"],
    )
    def test_an_answer_in_the_operator_s_view_reads_in_the_caller_s_whatever_member_does_not_read(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        body: str,
        request_id: str,
    ) -> None:
        """An answer holding diagnostics is projected onto the caller's view, its next step re-aimed, even when one of
        Pipelex's members does not read; only that member is left out, and the request id survives.
        """
        _install_hosted_api(mocker, monkeypatch, status=409, body=body, headers={"x-request-id": HEADER_REQUEST_ID})

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        assert json.loads(capsys.readouterr().err) == {**OperatorViewAnswers.CALLER_VIEW, "request_id": request_id}

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize("error_format", [CliOutputFormat.JSON, CliOutputFormat.MARKDOWN])
    def test_a_nested_run_s_record_reads_in_the_caller_s_view_in_an_answer_in_the_caller_s(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        error_format: CliOutputFormat,
    ) -> None:
        """A run's stored record nested in an answer is its operator's, so its operator-only next step is re-aimed at the
        caller even when no diagnostics tell its view; the answer around it keeps the runner's own step.
        """
        _install_hosted_api(mocker, monkeypatch, status=409, body=OperatorViewAnswers.NESTING_THE_OPERATOR_S_RECORD)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=error_format, runner=RunExecution.HOSTED)

        printed = capsys.readouterr().err
        sent = json.loads(OperatorViewAnswers.NESTING_THE_OPERATOR_S_RECORD)
        match error_format:
            case CliOutputFormat.JSON:
                assert json.loads(printed) == {**sent, "run_error": OperatorViewAnswers.CALLER_VIEW}
            case CliOutputFormat.MARKDOWN:
                assert f"**Next step** (`report`): {OperatorViewAnswers.CALLER_VIEW['next_step']['detail']}" in printed
                assert sent["run_error"]["next_step"]["detail"] not in printed
                assert f"**Next step** (`read_run`): {sent['next_step']['detail']}" in printed

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize("error_format", [CliOutputFormat.JSON, CliOutputFormat.MARKDOWN])
    @pytest.mark.parametrize(
        ("body", "keeps_run_error"),
        list(zip(OperatorViewAnswers.HOSTILE, (False, False, False, True), strict=True)),
        ids=["run_error_text", "run_error_unreadable", "every_member_unreadable", "nested_members_unreadable"],
    )
    def test_no_member_a_runner_answers_stops_the_report(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        body: str,
        keeps_run_error: bool,
        error_format: CliOutputFormat,
    ) -> None:
        """Pipelex's members in any shape, the nested run's problem included, leave the command reporting the runner's problem:
        each member that does not read is left out alone, so a nested problem whose own members do not read is kept without them.
        """
        _install_hosted_api(mocker, monkeypatch, status=409, body=body)

        with pytest.raises(typer.Exit) as exc_info:
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=error_format, runner=RunExecution.HOSTED)

        assert exc_info.value.exit_code == 1
        printed = capsys.readouterr().err
        match error_format:
            case CliOutputFormat.JSON:
                problem = json.loads(printed)
                assert problem["code"] == "run.terminated"
                assert "diagnostics" not in problem
                assert "request_id" not in problem
                if keeps_run_error:
                    assert problem["run_error"] == OperatorViewAnswers.CALLER_VIEW
                else:
                    assert "run_error" not in problem
            case CliOutputFormat.MARKDOWN:
                assert printed.startswith("## The run was stopped by an operator or an erasure\n")

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

    @pytest.mark.usefixtures("tty_stdin")
    @pytest.mark.parametrize(
        ("status", "body", "expected"),
        [
            # A runner's problem document, naming its code and its domain.
            (422, RunnerProblems.INPUT_MISSING, UsageStatsError(code="input.missing", domain=UsageStatsErrorDomain.INPUT)),
            # A gateway's page: pipelex-sdk reads a problem from the status, which the hosted API never sent.
            (502, GatewayAnswers.HTML_PAGE, None),
        ],
        ids=["runner_problem", "gateway_page"],
    )
    def test_the_statistics_record_what_the_hosted_api_sent(
        self,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        bundle_file: Path,
        status: int,
        body: str,
        expected: UsageStatsError | None,
    ) -> None:
        """The command's statistics record the code and domain the hosted API sent, never the client's reading of a status."""
        _install_hosted_api(mocker, monkeypatch, status=status, body=body)
        noted = mocker.patch("pipelex.cli.agent_cli.commands.agent_output.note_command_error")

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        capsys.readouterr()
        if expected is None:
            noted.assert_not_called()
        else:
            noted.assert_called_once_with(error=expected)

    @pytest.mark.usefixtures("tty_stdin")
    def test_the_statistics_record_an_unreachable_runner_as_the_client_decided(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        _install_unreachable_api(mocker, monkeypatch)
        noted = mocker.patch("pipelex.cli.agent_cli.commands.agent_output.note_command_error")

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        capsys.readouterr()
        noted.assert_called_once_with(error=UsageStatsError(code="client.unreachable", domain=UsageStatsErrorDomain.RUNTIME))
