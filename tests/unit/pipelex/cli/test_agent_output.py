from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

import pytest
import typer
from mthds.protocol.problem.registry import CoreCode
from typer.testing import CliRunner

from pipelex.base_exceptions import PipelexConfigError, PipelexError
from pipelex.cli.agent_cli._agent_cli import app
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_argument_error,
    agent_error,
    agent_file_error,
    agent_success,
    get_agent_cli_error_format,
    problem_payload,
    render_problem_markdown,
    set_agent_cli_error_format,
    start_agent_cli_error_format,
    use_agent_cli_error_format,
)
from pipelex.cli.commands.run.exceptions import AmbiguousInputsFilesError
from pipelex.cogt.exceptions import InferenceBackendCredentialsError, InferenceBackendCredentialsErrorType
from pipelex.errors.problem import MigrationErrorBlock, ProblemView, make_location, make_problem, make_problem_item
from pipelex.pipe_run.located_failure import make_unexpected_failure
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.system.usage_stats.usage_stats_contract import UsageStatsError, UsageStatsErrorDomain
from pipelex.tools.misc.exceptions import RemoteFileFetchError
from tests.helpers.recovered_problem import make_recovered_url_refusal

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture


def _url_refusal() -> RemoteFileFetchError:
    return RemoteFileFetchError("Could not fetch 'https://example.com/a.pdf': the request timed out").with_error_code(CoreCode.INPUT_URL_UNREACHABLE)


class TestAgentOutput:
    @pytest.fixture(autouse=True)
    def _restore_logging_cutoff(self) -> Iterator[None]:
        """Restore the process-global ``logging.disable`` threshold after a test that runs the app.

        The app callback arms the agent CLI cutoff through ``silence_logging_for_agent_cli``;
        left in place it silences every log call of every test that runs after this module.
        """
        original_disable = logging.root.manager.disable
        yield
        logging.disable(original_disable)

    # -------------------------------------------------------------------------
    # The JSON problem
    # -------------------------------------------------------------------------

    def test_agent_error_prints_the_problem_as_json_on_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A failure with no cause and no code is the registry's catch-all, the command's sentence riding as message."""
        with pytest.raises(typer.Exit) as exc_info:
            agent_error("something went wrong")
        assert exc_info.value.exit_code == 1

        captured = capsys.readouterr()
        assert captured.out == ""
        parsed = json.loads(captured.err)
        assert parsed["type"] == "https://mthds.ai/errors/runtime.unexpected"
        assert parsed["code"] == CoreCode.RUNTIME_UNEXPECTED
        assert parsed["domain"] == "runtime"
        assert parsed["message"] == "something went wrong"
        for retired in ("error", "error_type", "error_domain", "error_code", "hint", "retryable", "error_source", "validation_errors"):
            assert retired not in parsed

    def test_agent_error_names_the_code_of_a_refusal_the_command_decides(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            agent_argument_error("--yes contradicts --dry-run", argument="--yes", reason="contradicts --dry-run", exit_code=2)
        assert exc_info.value.exit_code == 2

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == CoreCode.CLIENT_ARGUMENT_INVALID
        assert parsed["domain"] == "input"
        assert parsed["retry"] == "no"
        assert parsed["params"] == {"argument": "--yes", "reason": "contradicts --dry-run"}
        assert parsed["detail"] == "The argument '--yes' was refused before any request left (reason: contradicts --dry-run)."
        assert parsed["next_step"] == {"kind": "change_input", "detail": "Correct the argument '--yes', then try again."}
        assert parsed["message"] == "--yes contradicts --dry-run"
        assert "diagnostics" not in parsed

    def test_agent_file_error_names_the_file_and_the_caught_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(typer.Exit):
            agent_file_error("Input file not found: inputs.json", path="inputs.json", reason="not found", cause=FileNotFoundError("inputs.json"))

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == CoreCode.CLIENT_FILE_UNREADABLE
        assert parsed["params"] == {"path": "inputs.json", "reason": "not found"}
        assert parsed["diagnostics"]["error_class"] == "FileNotFoundError"

    def test_agent_error_carries_the_command_s_own_members_beside_the_problem(self, capsys: pytest.CaptureFixture[str]) -> None:
        """The command's facts ride as further members, a datetime serialized, and none replaces a member of the problem."""
        with pytest.raises(typer.Exit):
            agent_error(
                "fail",
                pipe_code="my_pipe",
                custom_data=[1, 2],
                failed_at=datetime.datetime(2026, 2, 9, 14, 0, 0),
                code_hint="mine",
                detail="not the problem's",
            )

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["pipe_code"] == "my_pipe"
        assert parsed["custom_data"] == [1, 2]
        assert parsed["failed_at"] == "2026-02-09T14:00:00"
        assert parsed["code_hint"] == "mine"
        assert parsed["detail"] != "not the problem's"

    def test_problem_payload_never_lets_a_member_of_the_command_replace_the_problem_s(self) -> None:
        problem = make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR)
        payload = problem_payload(problem=problem, message="the command's sentence", extras={"code": "not.mine", "is_valid": False, "empty": None})
        assert payload["code"] == CoreCode.RUNTIME_UNEXPECTED
        assert payload["message"] == "the command's sentence"
        assert payload["is_valid"] is False
        assert "empty" not in payload

    def test_agent_error_reports_a_pipelex_cause_by_its_own_problem_in_the_operator_view(self, capsys: pytest.CaptureFixture[str]) -> None:
        cause = _url_refusal()
        with pytest.raises(typer.Exit):
            agent_error("fetch timed out", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        expected = cause.to_problem(view=ProblemView.OPERATOR).to_wire()
        for member in ("type", "title", "detail", "code", "domain", "retry", "next_step"):
            assert parsed[member] == expected[member]
        assert parsed["retry"] == "yes"
        assert parsed["diagnostics"]["error_class"] == "RemoteFileFetchError"

    def test_agent_error_classifies_a_recovered_problem_by_its_own_code(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A cause reporting a problem it recovered gives its code, domain and verdict together with its step, never its class's."""
        cause = make_recovered_url_refusal()
        problem = cause.to_problem(view=ProblemView.OPERATOR)
        with pytest.raises(typer.Exit):
            agent_error("the run failed on the worker", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == CoreCode.INPUT_URL_UNREACHABLE
        assert parsed["domain"] == "input"
        assert parsed["retry"] == "yes"
        assert parsed["next_step"]["detail"] == problem.next_step.detail

    def test_agent_error_lists_no_item_of_a_verdict_behind_a_foreign_exception(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A foreign exception raised from a handled verdict is a new failure: its problem lists none of the verdict's items."""
        stale_verdict = ValidateBundleError(message="validation failed", pipelex_bundle_blueprint_validation_errors=[])
        foreign_fault = RuntimeError("the cache could not be written")
        foreign_fault.__cause__ = stale_verdict
        stand_in = make_unexpected_failure(error=foreign_fault)

        with pytest.raises(typer.Exit):
            agent_error("unexpected failure", cause=stand_in)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == CoreCode.RUNTIME_UNEXPECTED
        assert "errors" not in parsed

    def test_agent_error_lists_the_items_of_a_verdict_under_pipelex_wrappers(self, capsys: pytest.CaptureFixture[str]) -> None:
        verdict = ValidateBundleError(message="Pipe 'post_notice' could not be loaded")
        wrapper = PipelexError("the run was refused")
        wrapper.__cause__ = verdict

        with pytest.raises(typer.Exit):
            agent_error("the run was refused", cause=wrapper)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == CoreCode.METHOD_INVALID
        assert [item["params"]["finding"] for item in parsed["errors"]] == ["Pipe 'post_notice' could not be loaded"]

    def test_agent_error_reports_a_foreign_cause_as_unexpected_with_its_class(self, capsys: pytest.CaptureFixture[str]) -> None:
        cause = RuntimeError("constructed, not raised")
        with pytest.raises(typer.Exit) as exc_info:
            agent_error("something broke", cause=cause)
        assert exc_info.value.exit_code == 1

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == CoreCode.RUNTIME_UNEXPECTED
        assert parsed["diagnostics"]["error_class"] == "RuntimeError"
        assert parsed["diagnostics"]["message"] == "constructed, not raised"

    def test_agent_error_names_the_provider_of_a_failed_backend(self, capsys: pytest.CaptureFixture[str]) -> None:
        cause = InferenceBackendCredentialsError(
            credentials_error_type=InferenceBackendCredentialsErrorType.VAR_NOT_FOUND,
            backend_name="openai",
            message="OPENAI_API_KEY not set",
            key_name="OPENAI_API_KEY",
        )
        with pytest.raises(typer.Exit):
            agent_error("OPENAI_API_KEY not set", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["code"] == "pipelex.config.credential_missing"
        assert parsed["domain"] == "operator"
        assert parsed["diagnostics"]["provider"] == {"name": "openai"}

    @pytest.mark.parametrize("error_format", [CliOutputFormat.JSON, CliOutputFormat.MARKDOWN])
    def test_a_pending_configuration_migration_rides_the_diagnostics(self, capsys: pytest.CaptureFixture[str], error_format: CliOutputFormat) -> None:
        migration = MigrationErrorBlock(remedy="pipelex-agent migrate --yes", would_write=True, needs_attention=False, plans=[])
        set_agent_cli_error_format(error_format)
        with pytest.raises(typer.Exit):
            agent_error("Pipelex initialization failed", cause=PipelexConfigError("bad config", migration=migration))

        err = capsys.readouterr().err
        match error_format:
            case CliOutputFormat.JSON:
                parsed = json.loads(err)
                assert parsed["code"] == "pipelex.config.invalid"
                assert parsed["diagnostics"]["migration"] == {
                    "remedy": "pipelex-agent migrate --yes",
                    "would_write": True,
                    "needs_attention": False,
                    "plans": [],
                }
            case CliOutputFormat.MARKDOWN:
                assert "### Configuration migration" in err
                assert "- Remedy: `pipelex-agent migrate --yes`" in err
                assert "- Would write: yes" in err
                assert "- Needs attention: no" in err

    def test_agent_error_notes_the_problem_s_code_for_the_usage_statistics(self, mocker: MockerFixture) -> None:
        noted = mocker.patch("pipelex.cli.agent_cli.commands.agent_output.note_command_error")
        with pytest.raises(typer.Exit):
            agent_argument_error("bad", argument="--yes", reason="contradicts --dry-run")
        noted.assert_called_once_with(error=UsageStatsError(code="client.argument_invalid", domain=UsageStatsErrorDomain.INPUT))

    # -------------------------------------------------------------------------
    # The Markdown problem
    # -------------------------------------------------------------------------

    def test_agent_error_renders_markdown_when_markdown_is_the_error_format(self, capsys: pytest.CaptureFixture[str]) -> None:
        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)
        with pytest.raises(typer.Exit) as exc_info:
            agent_argument_error("--yes contradicts --dry-run", argument="--yes", reason="contradicts --dry-run", pipe_code="my_pipe")
        assert exc_info.value.exit_code == 1

        captured = capsys.readouterr()
        assert captured.out == ""
        err = captured.err
        assert err.startswith("## An argument was refused before sending\n\nThe argument '--yes' was refused before any request left")
        assert "\n--yes contradicts --dry-run\n" in err
        assert "**Next step** (`change_input`): Correct the argument '--yes', then try again." in err
        assert "- Code: `client.argument_invalid` (domain input, retry no)" in err
        assert "### Details" in err
        assert "- **pipe_code:** my_pipe" in err
        with pytest.raises(json.JSONDecodeError):
            json.loads(err)

    def test_markdown_prints_the_advice_of_the_error_as_a_tip_the_json_never_carries(self, capsys: pytest.CaptureFixture[str]) -> None:
        cause = AmbiguousInputsFilesError("Directory 'd' holds both 'inputs.json' and 'inputs.toml'")
        advice = cause.advised_action()
        assert advice is not None

        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)
        with pytest.raises(typer.Exit):
            agent_error(cause.message, cause=cause)
        assert f"\n💡 {advice.detail}\n" in capsys.readouterr().err

        set_agent_cli_error_format(CliOutputFormat.JSON)
        with pytest.raises(typer.Exit):
            agent_error(cause.message, cause=cause)
        assert advice.detail not in capsys.readouterr().err

    def test_render_problem_markdown_states_the_facts_the_faults_and_the_diagnostics(self) -> None:
        location = make_location(pipe="summarize", path=["main", "summarize"], file="contracts.mthds", line=12)
        item = make_problem_item(code=CoreCode.METHOD_CONCEPT_UNRESOLVED, params={"concept": "Missing"}, location=make_location(pipe="summarize"))
        problem = make_problem(
            code=CoreCode.METHOD_INVALID,
            view=ProblemView.OPERATOR,
            location=location,
            errors=[item],
            request_id="req-123",
            pipeline_run_id="run-456",
        )

        rendered = render_problem_markdown(problem=problem, message=problem.detail, extras={"is_valid": False, "bundle_path": "/w/b.mthds"})

        assert rendered.startswith(f"## {problem.title}\n\n{problem.detail}\n\n**Next step**")
        assert f"\n{problem.detail}\n\n{problem.detail}" not in rendered
        assert "- Code: `method.invalid` (domain method, retry no)" in rendered
        assert "- Request id: `req-123`" in rendered
        assert "- Run: `run-456`" in rendered
        assert "- Location: pipe 'summarize', path main > summarize, file 'contracts.mthds', line 12" in rendered
        assert "### Errors" in rendered
        assert f"- `method.concept_unresolved`: {item.detail} (pipe 'summarize')" in rendered
        assert "- **bundle_path:** /w/b.mthds" in rendered
        assert "is_valid" not in rendered

    def test_render_problem_markdown_nests_the_run_s_own_problem(self) -> None:
        """A read of a failed run's results renders the run's own problem under it: its sentence, step, code, location and items."""
        item = make_problem_item(code=CoreCode.METHOD_CONCEPT_UNRESOLVED, params={"concept": "Missing"}, location=make_location(pipe="summarize"))
        run_error = make_problem(code=CoreCode.METHOD_INVALID, view=ProblemView.CALLER, location=make_location(pipe="summarize"), errors=[item])
        read = make_problem(
            code=CoreCode.RUN_FAILED, view=ProblemView.CALLER, params={"pipeline_run_id": "run-9", "run_status": "FAILED"}, pipeline_run_id="run-9"
        ).with_members(run_error=run_error.to_wire())

        rendered = render_problem_markdown(problem=read)

        assert "- Code: `run.failed` (domain runtime, retry no)" in rendered
        assert (
            f"### The run's own problem\n\n**{run_error.title}**: {run_error.detail}\n\n"
            f"**Next step** (`{run_error.next_step.kind}`): {run_error.next_step.detail}\n\n"
            "- Code: `method.invalid` (domain method, retry no)\n- Location: pipe 'summarize'\n\n"
            f"#### The run's errors\n\n- `method.concept_unresolved`: {item.detail} (pipe 'summarize')"
        ) in rendered

    def test_render_problem_markdown_names_the_model_and_the_provider(self) -> None:
        cause = InferenceBackendCredentialsError(
            credentials_error_type=InferenceBackendCredentialsErrorType.VAR_NOT_FOUND,
            backend_name="openai",
            message="OPENAI_API_KEY not set",
            key_name="OPENAI_API_KEY",
        )
        rendered = render_problem_markdown(problem=cause.to_problem(view=ProblemView.OPERATOR))
        assert "### Diagnostics" in rendered
        assert "- Error class: `InferenceBackendCredentialsError`" in rendered
        assert "- Provider: `openai`" in rendered

    # -------------------------------------------------------------------------
    # The error format: the command's, the program's, the command's --format
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize(
        ("command_error_format", "root_error_format", "output_format", "expected"),
        [
            (None, None, None, CliOutputFormat.JSON),
            (None, None, CliOutputFormat.MARKDOWN, CliOutputFormat.MARKDOWN),
            (None, CliOutputFormat.JSON, CliOutputFormat.MARKDOWN, CliOutputFormat.JSON),
            (None, CliOutputFormat.MARKDOWN, CliOutputFormat.JSON, CliOutputFormat.MARKDOWN),
            (CliOutputFormat.JSON, CliOutputFormat.MARKDOWN, CliOutputFormat.MARKDOWN, CliOutputFormat.JSON),
            (CliOutputFormat.MARKDOWN, None, None, CliOutputFormat.MARKDOWN),
        ],
    )
    def test_the_error_format_is_the_command_s_then_the_program_s_then_the_format(
        self,
        command_error_format: CliOutputFormat | None,
        root_error_format: CliOutputFormat | None,
        output_format: CliOutputFormat | None,
        expected: CliOutputFormat,
    ) -> None:
        start_agent_cli_error_format(root_error_format=root_error_format)
        use_agent_cli_error_format(error_format=command_error_format, output_format=output_format)
        assert get_agent_cli_error_format() == expected

    def test_app_callback_resets_error_format_to_json(self, mocker: MockerFixture) -> None:
        """The error format is reset per invocation: a markdown command leaving it set must not leak into a later one."""
        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)
        mocker.patch("pipelex.cli.agent_cli.commands.plxt_passthrough.shutil.which", return_value=None)

        # `fmt` has no --format / --error-format option; with no plxt binary on the path it errors via agent_error().
        result = CliRunner().invoke(app, ["fmt", "bundle.mthds"])

        assert result.exit_code == 1
        parsed = json.loads(result.stderr)
        assert parsed["code"] == CoreCode.CLIENT_TOOL_MISSING
        assert parsed["params"] == {"tool": "plxt"}

    def test_the_program_s_error_format_reaches_a_command_with_no_option_of_its_own(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.cli.agent_cli.commands.plxt_passthrough.shutil.which", return_value=None)

        result = CliRunner().invoke(app, ["--error-format", "markdown", "fmt", "bundle.mthds"])

        assert result.exit_code == 1
        assert result.stderr.startswith("## A local tool the client needs is missing")
        assert "- Code: `client.tool_missing`" in result.stderr

    @pytest.mark.parametrize(
        ("args", "is_markdown"),
        [
            (["no-such-command"], False),
            (["--error-format", "markdown", "no-such-command"], True),
        ],
    )
    def test_an_unknown_command_is_an_argument_refusal_in_the_program_s_error_format(self, args: list[str], is_markdown: bool) -> None:
        result = CliRunner().invoke(app, args)

        assert result.exit_code == 1
        if is_markdown:
            assert result.stderr.startswith("## An argument was refused before sending")
            assert "Unknown command: no-such-command" in result.stderr
        else:
            parsed: dict[str, Any] = json.loads(result.stderr)
            assert parsed["code"] == CoreCode.CLIENT_ARGUMENT_INVALID
            assert parsed["params"] == {"argument": "no-such-command", "reason": "not a command of pipelex-agent"}
            assert "validate" in parsed["valid_commands"]

    # -------------------------------------------------------------------------
    # Success output
    # -------------------------------------------------------------------------

    def test_agent_success_outputs_json_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        agent_success({"success": True, "value": 42})

        captured = capsys.readouterr()
        assert captured.err == ""
        parsed = json.loads(captured.out)
        assert parsed["success"] is True
        assert parsed["value"] == 42

    @pytest.mark.parametrize(
        ("label", "value", "expected_iso"),
        [
            ("date", datetime.date(2026, 1, 15), "2026-01-15"),
            ("datetime", datetime.datetime(2026, 1, 15, 10, 30, 0), "2026-01-15T10:30:00"),
            ("time", datetime.time(10, 30, 0), "10:30:00"),
        ],
    )
    def test_agent_success_handles_datetime_types(
        self,
        capsys: pytest.CaptureFixture[str],
        label: str,
        value: datetime.date | datetime.datetime | datetime.time,
        expected_iso: str,
    ) -> None:
        """agent_success must serialize datetime/date/time values without raising."""
        agent_success({"success": True, "field": value})

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        assert parsed["field"] == expected_iso, f"Expected ISO format for {label}"

    def test_agent_success_handles_nested_datetime(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = {
            "success": True,
            "working_memory": {
                "report_data": {
                    "report_date": datetime.date(2026, 3, 1),
                    "items": [
                        {"timestamp": datetime.datetime(2026, 3, 1, 9, 0, 0)},
                    ],
                },
            },
        }
        agent_success(result)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["working_memory"]["report_data"]["report_date"] == "2026-03-01"
        assert parsed["working_memory"]["report_data"]["items"][0]["timestamp"] == "2026-03-01T09:00:00"
