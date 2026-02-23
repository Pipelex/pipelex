"""Unit tests for the agent CLI output helpers."""

from __future__ import annotations

import datetime
import json

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import (
    AGENT_ERROR_HINTS,
    _build_error_source,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    agent_error,
    agent_success,
    extract_validation_errors,
)
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintValidationErrorData
from pipelex.core.exceptions import PipeFactoryErrorData, PipesAndConceptValidationErrorData
from pipelex.core.pipes.exceptions import PipeFactoryErrorType, PipeValidationErrorType
from pipelex.pipeline.validate_bundle import ValidateBundleError


class TestAgentOutput:
    """Tests for agent_error, agent_success, and extract_validation_errors."""

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
            pipe_concept_instantiation_errors=[
                PipesAndConceptValidationErrorData(
                    error_type=PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR,
                    pipe_code="pipe_d",
                    message="pydantic validation failed",
                    field_path="pipe_d.output",
                ),
            ],
        )

        result = extract_validation_errors(exc)
        assert len(result) == 4

        categories = [entry["category"] for entry in result]
        assert "blueprint_validation" in categories
        assert "pipe_factory" in categories
        assert "pipe_validation" in categories
        assert "instantiation" in categories

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
