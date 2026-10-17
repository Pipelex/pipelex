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
from pipelex.hosted.run_config import RunExecution
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsError, UsageStatsErrorDomain
from tests.unit.pipelex.cli.agent_cli.test_data import GatewayAnswers, RetiredEnvelope, RunnerProblems
from tests.unit.pipelex.hosted.test_data import HostedVersions

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

HOSTED_URL = "https://hosted.test"
RUN_PIPE_MODULE = "pipelex.cli.agent_cli.commands.run.pipe_cmd"
START_ROUTE = ("POST", "/v1/start")
#: The problem pipelex-sdk decides for a runner that cannot be reached at `HOSTED_URL`, the base client's own.
UNREACHABLE_PROBLEM: dict[str, Any] = {
    "type": "https://mthds.ai/errors/client.unreachable",
    "title": "The runtime could not be reached",
    "detail": f"The client could not connect to the runtime at {HOSTED_URL}.",
    "code": "client.unreachable",
    "domain": "runtime",
    "retry": "yes",
    "next_step": {"kind": "retry", "detail": f"Check that the runtime at {HOSTED_URL} is up and reachable, then try again."},
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


def _answering(*, status: int, body: str, seen: list[httpx.Request]) -> httpx.MockTransport:
    """A hosted API that answers its version, then refuses every other request with ``status`` and ``body``."""

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET" and request.url.path == "/v1/version":
            return httpx.Response(200, content=HostedVersions.HOSTED.encode("utf-8"), headers={"content-type": "application/json"})
        return httpx.Response(status, content=body.encode("utf-8"), headers={"content-type": "application/problem+json"})

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


def _install_hosted_api(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, *, status: int, body: str) -> list[httpx.Request]:
    """Point every `PipelexAPIClient` at a mocked hosted API refusing with ``status`` / ``body``; return the requests it receives."""
    seen: list[httpx.Request] = []
    _install_transport(mocker, monkeypatch, transport=_answering(status=status, body=body, seen=seen))
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
        assert f"**Next step** (`retry`): Check that the runtime at {HOSTED_URL} is up and reachable, then try again." in markdown
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
    def test_a_server_without_the_run_routes_is_the_client_s_reading_of_its_answer(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], bundle_file: Path
    ) -> None:
        """A server with neither `/v1/start` nor `/v1/execute` answers no problem document, so its 404 is read from the status."""
        seen = _install_hosted_api(mocker, monkeypatch, status=404, body=GatewayAnswers.NOT_FOUND)

        with pytest.raises(typer.Exit):
            run_bundle_cmd(path=str(bundle_file), pipe="entry", output_format=CliOutputFormat.JSON, runner=RunExecution.HOSTED)

        # The SDK falls back to a blocking execute when the run routes are absent, as a bare runner serves.
        assert _routes(seen=seen) == [START_ROUTE, ("POST", "/v1/execute")]
        problem = json.loads(capsys.readouterr().err)
        assert problem["code"] == "client.response_unreadable"
        assert problem["params"] == {"status": 404}
        _assert_no_retired_member(problem=problem)

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
