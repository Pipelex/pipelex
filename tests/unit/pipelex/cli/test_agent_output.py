"""Unit tests for the agent CLI output helpers."""

from __future__ import annotations

import json

import pytest
import typer

from pipelex.cli.agent_cli.commands.agent_output import (
    AGENT_ERROR_HINTS,
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

    def test_extract_validation_errors_empty(self) -> None:
        """extract_validation_errors should return empty list when no errors."""
        exc = ValidateBundleError(message="no details")
        result = extract_validation_errors(exc)
        assert result == []
