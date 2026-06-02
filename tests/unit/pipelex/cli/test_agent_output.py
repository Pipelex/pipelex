"""Unit tests for the agent CLI output helpers."""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING, Any

import pytest
import typer
from typer.testing import CliRunner

from pipelex.base_exceptions import PipelexConfigError, PipelexError
from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError
from pipelex.cli.agent_cli._agent_cli import app  # noqa: PLC2701
from pipelex.cli.agent_cli.commands.agent_output import (
    AGENT_ERROR_DOMAINS,
    AGENT_ERROR_HINTS,
    CliOutputFormat,
    _build_error_source,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    agent_error,
    agent_success,
    consume_setup_warnings,
    extract_validation_errors,
    record_setup_warning,
    set_agent_cli_error_format,
)
from pipelex.cogt.exceptions import CogtError, InferenceBackendCredentialsError, InferenceBackendCredentialsErrorType, InferenceErrorCategory
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.exceptions import PipeFactoryErrorData, PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeFactoryErrorType, PipeValidationErrorType
from pipelex.pipeline.exceptions import ValidateBundleError

if TYPE_CHECKING:
    from collections.abc import Iterator


class TestAgentOutput:
    """Tests for agent_error, agent_success, and extract_validation_errors."""

    @pytest.fixture(autouse=True)
    def _drain_warnings_buffer(self) -> Iterator[None]:
        """Isolate the module-level ``_CAPTURED_WARNINGS`` global across tests.

        The buffer is a process-wide global; without this drain a recorded warning
        could leak into an unrelated test's envelope.
        """
        consume_setup_warnings()
        yield
        consume_setup_warnings()

    def test_agent_error_outputs_json_to_stderr(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should print valid JSON to stderr and exit with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            agent_error("something went wrong", "TestError")
        assert exc_info.value.exit_code == 1

        captured = capsys.readouterr()
        assert captured.out == ""
        parsed = json.loads(captured.err)
        assert parsed["error"] is True
        assert parsed["error_type"] == "TestError"
        assert parsed["message"] == "something went wrong"

    def test_agent_error_includes_hint_for_known_type(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should auto-add a hint for known error types."""
        with pytest.raises(typer.Exit):
            agent_error("model issue", "PipeOperatorModelChoiceError")

        parsed = json.loads(capsys.readouterr().err)
        assert "hint" in parsed
        assert parsed["hint"] == AGENT_ERROR_HINTS["PipeOperatorModelChoiceError"]

    def test_agent_error_includes_signature_hint(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A SignaturesNotAllowedError surfaced through the agent boundary must carry the --allow-signatures hint.

        The agent CLI's strict `validate pipe --all` / single-pipe paths surface this error through
        agent_error with the exception as cause. The hint still comes from the AGENT_ERROR_HINTS
        fallback (the class declares no class-level user_action), while error_domain now flows from the
        exception's class-level INPUT classification rather than the AGENT_ERROR_DOMAINS dict.
        """
        cause = SignaturesNotAllowedError(offending_pipe_refs={"d.caller"}, signature_refs={"d.summary_sig"}, dep_paths={})
        with pytest.raises(typer.Exit):
            agent_error("strict validation reached a PipeSignature", "SignaturesNotAllowedError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["hint"] == AGENT_ERROR_HINTS["SignaturesNotAllowedError"]
        assert "--allow-signatures" in parsed["hint"]
        # error_domain is now sourced from the class-level metadata (INPUT), not the lookup dict.
        assert parsed["error_domain"] == "input"

    def test_agent_error_no_hint_for_unknown_type(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should not include hint for unregistered error types."""
        with pytest.raises(typer.Exit):
            agent_error("oops", "CompletelyUnknownError")

        parsed = json.loads(capsys.readouterr().err)
        assert "hint" not in parsed

    def test_agent_error_includes_extra_fields(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Extra kwargs should appear as top-level fields in the JSON output."""
        with pytest.raises(typer.Exit):
            agent_error("fail", "SomeError", pipe_code="my_pipe", custom_data=[1, 2])

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["pipe_code"] == "my_pipe"
        assert parsed["custom_data"] == [1, 2]

    def test_agent_error_extra_can_override_hint(self, capsys: pytest.CaptureFixture[str]) -> None:
        """An explicit hint kwarg should override the auto-looked-up hint."""
        with pytest.raises(typer.Exit):
            agent_error("fail", "ValidateBundleError", hint="custom hint")

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["hint"] == "custom hint"

    def test_agent_success_outputs_json_to_stdout(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_success should print valid JSON to stdout."""
        agent_success({"success": True, "value": 42})

        captured = capsys.readouterr()
        assert captured.err == ""
        parsed = json.loads(captured.out)
        assert parsed["success"] is True
        assert parsed["value"] == 42

    def test_extract_validation_errors_all_categories(self) -> None:
        """extract_validation_errors should return entries from all 4 categories."""
        exc = ValidateBundleError(
            message="validation failed",
            pipelex_bundle_blueprint_validation_errors=[
                PipelexBundleBlueprintValidationErrorData(
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    pipe_code="pipe_a",
                    message="missing var x",
                    variable_names=["x"],
                ),
            ],
            pipe_factory_errors=[
                PipeFactoryErrorData(
                    error_type=PipeFactoryErrorType.UNKNOWN_CONCEPT,
                    pipe_code="pipe_b",
                    message="concept Foo not found",
                    missing_concept_code="Foo",
                    declared_concepts=["Bar", "Baz"],
                ),
            ],
            pipe_validation_errors=[
                PipesAndConceptValidationErrorData(
                    error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    pipe_code="pipe_c",
                    message="extra var y",
                    field_path="pipe_c.inputs.y",
                    variable_names=["y"],
                ),
            ],
        )

        result = extract_validation_errors(exc)
        assert len(result) == 3

        categories = [entry["category"] for entry in result]
        assert "blueprint_validation" in categories
        assert "pipe_factory" in categories
        assert "pipe_validation" in categories

        # Check factory error has extra fields
        factory_entry = next(entry for entry in result if entry["category"] == "pipe_factory")
        assert factory_entry["missing_concept_code"] == "Foo"
        assert factory_entry["declared_concepts"] == ["Bar", "Baz"]

        # Check blueprint entry has variable_names
        blueprint_entry = next(entry for entry in result if entry["category"] == "blueprint_validation")
        assert blueprint_entry["variable_names"] == ["x"]

    # -------------------------------------------------------------------------
    # Datetime serialization tests (regression for "Object of type datetime is
    # not JSON serializable" bug in dry-run output)
    # -------------------------------------------------------------------------

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
        """agent_success must handle datetime objects nested in dicts and lists."""
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

    def test_agent_error_handles_datetime_in_extras(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error must serialize datetime values passed via **extra kwargs."""
        with pytest.raises(typer.Exit):
            agent_error(
                "pipeline failed",
                "PipelineExecutionError",
                failed_at=datetime.datetime(2026, 2, 9, 14, 0, 0),
            )

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert parsed["failed_at"] == "2026-02-09T14:00:00"

    def test_extract_validation_errors_empty(self) -> None:
        """extract_validation_errors should return empty list when no errors."""
        exc = ValidateBundleError(message="no details")
        result = extract_validation_errors(exc)
        assert result == []

    # -------------------------------------------------------------------------
    # _build_error_source tests
    # -------------------------------------------------------------------------

    def test_build_error_source_with_none_traceback(self) -> None:
        """_build_error_source should handle exceptions with no traceback (constructed but never raised)."""
        exc = RuntimeError("constructed, not raised")
        assert exc.__traceback__ is None

        sources = _build_error_source(exc)
        assert len(sources) == 1
        assert "RuntimeError" in sources[0]
        assert "no traceback" in sources[0]

    def test_build_error_source_with_chained_none_tracebacks(self) -> None:
        """_build_error_source should handle a cause chain where all exceptions lack tracebacks."""
        cause = ValueError("root cause")
        outer = RuntimeError("wrapper")
        outer.__cause__ = cause
        assert cause.__traceback__ is None
        assert outer.__traceback__ is None

        sources = _build_error_source(outer)
        assert len(sources) == 2
        assert "RuntimeError" in sources[0]
        assert "no traceback" in sources[0]
        assert "ValueError" in sources[1]
        assert "no traceback" in sources[1]

    def test_build_error_source_with_real_traceback(self) -> None:
        """_build_error_source should extract location info from a raised exception."""
        try:
            msg = "actually raised"
            raise RuntimeError(msg)
        except RuntimeError as exc:
            sources = _build_error_source(exc)

        assert len(sources) == 1
        assert "RuntimeError" in sources[0]
        assert "no traceback" not in sources[0]
        assert "test_agent_output.py" in sources[0]

    def test_agent_error_with_no_traceback_cause(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should emit valid JSON even when cause has no traceback."""
        cause = RuntimeError("constructed, not raised")
        assert cause.__traceback__ is None

        with pytest.raises(typer.Exit) as exc_info:
            agent_error("something broke", "RuntimeError", cause=cause)
        assert exc_info.value.exit_code == 1

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert "error_source" in parsed
        assert len(parsed["error_source"]) == 1
        assert "no traceback" in parsed["error_source"][0]

    # -------------------------------------------------------------------------
    # to_error_report() integration tests
    # -------------------------------------------------------------------------

    def test_agent_error_uses_report_hint_from_cogt_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should use user_action from to_error_report() as the hint field."""
        cause = CogtError(
            "inference failed",
            user_action=UserAction(kind=UserActionKind.CHECK_CREDENTIALS, detail="Check your API key and try again"),
        )
        with pytest.raises(typer.Exit):
            agent_error("inference failed", "CogtError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["hint"] == "Check your API key and try again"

    def test_agent_error_uses_report_retryable_from_cogt_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should set retryable=True when error_category is TRANSIENT."""
        cause = CogtError("rate limited", error_category=InferenceErrorCategory.TRANSIENT)
        with pytest.raises(typer.Exit):
            agent_error("rate limited", "CogtError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["retryable"] is True

    def test_agent_error_uses_report_error_category(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should include error_category from to_error_report()."""
        cause = CogtError("bad config", error_category=InferenceErrorCategory.CONFIGURATION)
        with pytest.raises(typer.Exit):
            agent_error("bad config", "CogtError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error_category"] == "configuration"

    def test_agent_error_falls_back_to_lookup_for_non_pipelex_error(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should use lookup dicts when cause is not a PipelexError."""
        cause = FileNotFoundError("missing.mthds")
        with pytest.raises(typer.Exit):
            agent_error("file not found", "FileNotFoundError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["hint"] == AGENT_ERROR_HINTS["FileNotFoundError"]
        assert "error_category" not in parsed

    def test_agent_error_falls_back_to_lookup_when_report_fields_none(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should fall back to lookup when PipelexError has no category/user_action."""
        cause = PipelexError("something failed")
        with pytest.raises(typer.Exit):
            agent_error("something failed", "PipeExecutionError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        # hint should come from AGENT_ERROR_HINTS since PipelexError has no user_action
        assert parsed["hint"] == AGENT_ERROR_HINTS["PipeExecutionError"]

    def test_agent_error_report_hint_overrides_lookup(self, capsys: pytest.CaptureFixture[str]) -> None:
        """When cause has user_action, it should override the lookup dict hint."""
        # Use an error_type that exists in AGENT_ERROR_HINTS
        cause = CogtError(
            "model not found",
            user_action=UserAction(kind=UserActionKind.CHANGE_MODEL, detail="Use pipelex-agent models to list available models"),
        )
        with pytest.raises(typer.Exit):
            agent_error("model not found", "ModelChoiceNotFoundError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["hint"] == "Use pipelex-agent models to list available models"
        assert parsed["hint"] != AGENT_ERROR_HINTS["ModelChoiceNotFoundError"]

    def test_agent_error_extra_still_overrides_report(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Explicit **extra kwargs should override report-derived fields."""
        cause = CogtError(
            "failed",
            user_action=UserAction(kind=UserActionKind.UNKNOWN, detail="from report"),
        )
        with pytest.raises(typer.Exit):
            agent_error("failed", "CogtError", cause=cause, hint="custom override")

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["hint"] == "custom override"

    def test_agent_error_includes_model_and_provider_from_report(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should include model and provider from to_error_report()."""
        cause = InferenceBackendCredentialsError(
            credentials_error_type=InferenceBackendCredentialsErrorType.VAR_NOT_FOUND,
            backend_name="openai",
            message="OPENAI_API_KEY not set",
            key_name="OPENAI_API_KEY",
        )
        with pytest.raises(typer.Exit):
            agent_error("OPENAI_API_KEY not set", "InferenceBackendCredentialsError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["provider"] == "openai"

    def test_agent_error_non_retryable_not_in_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Non-retryable errors should not include retryable field in JSON output."""
        cause = CogtError("bad config", error_category=InferenceErrorCategory.CONFIGURATION)
        with pytest.raises(typer.Exit):
            agent_error("bad config", "CogtError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert "retryable" not in parsed

    def test_agent_error_error_domain_and_category_coexist(self, capsys: pytest.CaptureFixture[str]) -> None:
        """error_domain (from lookup) and error_category (from report) should both appear."""
        # Use an error_type that is in AGENT_ERROR_DOMAINS
        error_type = "ModelChoiceNotFoundError"
        assert error_type in AGENT_ERROR_DOMAINS, "precondition: error_type must be in AGENT_ERROR_DOMAINS"

        cause = CogtError("model not found", error_category=InferenceErrorCategory.CONFIGURATION)
        with pytest.raises(typer.Exit):
            agent_error("model not found", error_type, cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error_domain"] == AGENT_ERROR_DOMAINS[error_type]
        assert parsed["error_category"] == "configuration"

    def test_agent_error_uses_report_error_domain(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should include error_domain from to_error_report() for a PipelexError cause."""
        cause = PipelexConfigError("bad config")
        with pytest.raises(typer.Exit):
            agent_error("bad config", "PipelexConfigError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error_domain"] == "config"

    def test_agent_error_error_domain_falls_back_to_dict_for_builtin(self, capsys: pytest.CaptureFixture[str]) -> None:
        """agent_error should read error_domain from the lookup dict for a non-PipelexError cause."""
        cause = FileNotFoundError("missing.mthds")
        with pytest.raises(typer.Exit):
            agent_error("file not found", "FileNotFoundError", cause=cause)

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error_domain"] == "input"

    def test_app_callback_resets_error_format_to_json(self) -> None:
        """The error-format ContextVar must be reset per invocation: a markdown command leaving
        it set must not leak markdown into a later JSON-only command in the same process.
        """
        # Simulate a prior markdown command having left the ContextVar set.
        set_agent_cli_error_format(CliOutputFormat.MARKDOWN)

        # `concept` is a JSON-only command with no --format / --error-format option; invoked with no spec it
        # errors via agent_error(). Its error must be JSON, proving the callback reset the format.
        result = CliRunner().invoke(app, ["concept"])

        assert result.exit_code == 1
        parsed = json.loads(result.stderr)
        assert parsed["error"] is True
        assert parsed["error_type"] == "ArgumentError"

    # -------------------------------------------------------------------------
    # Setup-warnings buffer tests (record_setup_warning / consume_setup_warnings
    # / the warnings-merge branch of agent_success)
    # -------------------------------------------------------------------------

    def test_agent_success_attaches_recorded_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A warning recorded via record_setup_warning surfaces in the envelope's warnings array."""
        record_setup_warning({"type": "RemoteConfigStale", "message": "cache is stale"})
        agent_success({"success": True})

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["warnings"] == [{"type": "RemoteConfigStale", "message": "cache is stale"}]

    def test_agent_success_does_not_re_emit_drained_warnings(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A second agent_success in the same process emits no stale warnings (drain+clear)."""
        record_setup_warning({"type": "RemoteConfigStale", "message": "cache is stale"})
        agent_success({"success": True})
        capsys.readouterr()  # discard the first envelope

        agent_success({"success": True})
        parsed = json.loads(capsys.readouterr().out)
        assert "warnings" not in parsed

    def test_consume_setup_warnings_drains_and_clears(self) -> None:
        """consume_setup_warnings returns the recorded list and empties the buffer."""
        record_setup_warning({"type": "RemoteConfigStale", "message": "first"})
        record_setup_warning({"type": "RemoteConfigStale", "message": "second"})

        drained = consume_setup_warnings()
        assert drained == [
            {"type": "RemoteConfigStale", "message": "first"},
            {"type": "RemoteConfigStale", "message": "second"},
        ]
        assert consume_setup_warnings() == []

    def test_agent_success_appends_captured_after_caller_warnings(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Caller-supplied result['warnings'] are kept; captured ones are appended after them."""
        record_setup_warning({"type": "RemoteConfigStale", "message": "captured"})
        agent_success({"success": True, "warnings": [{"type": "CallerWarning", "message": "caller"}]})

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["warnings"] == [
            {"type": "CallerWarning", "message": "caller"},
            {"type": "RemoteConfigStale", "message": "captured"},
        ]

    def test_agent_success_tolerates_non_list_caller_warnings(self, capsys: pytest.CaptureFixture[str]) -> None:
        """A non-list result['warnings'] is treated as empty rather than crashing (isinstance guard)."""
        record_setup_warning({"type": "RemoteConfigStale", "message": "captured"})
        agent_success({"success": True, "warnings": "not-a-list"})

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["warnings"] == [{"type": "RemoteConfigStale", "message": "captured"}]

    def test_agent_success_does_not_mutate_caller_result(self) -> None:
        """agent_success copies result before merging captured warnings; the caller dict is untouched."""
        record_setup_warning({"type": "RemoteConfigStale", "message": "captured"})
        result: dict[str, Any] = {"success": True}
        agent_success(result)

        assert "warnings" not in result
