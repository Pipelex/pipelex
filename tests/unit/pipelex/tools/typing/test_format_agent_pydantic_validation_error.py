import json
from typing import Any, ClassVar, Literal

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing_extensions import override

from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error_for_agent


class _SimpleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    age: int


class _LiteralModel(BaseModel):
    tone: Literal["Casual", "Professional", "Academic"] = Field(..., description="Tone")


class _NonSerializable:
    """An object that is not JSON-serializable."""

    @override
    def __repr__(self) -> str:
        return "<NonSerializable>"


class TestData:
    MISSING_FIELD: ClassVar[tuple[dict[str, Any], str]] = (
        {"age": 25},
        "missing_fields",
    )
    EXTRA_FIELD: ClassVar[tuple[dict[str, Any], str]] = (
        {"name": "Alice", "age": 25, "unknown": "x"},
        "extra_fields",
    )
    LARGE_INPUT: ClassVar[tuple[dict[str, Any], str]] = (
        {"age": "A" * 500},
        "missing_fields",
    )
    MULTIPLE_ERRORS: ClassVar[tuple[dict[str, Any], str]] = (
        {"unknown": "x"},
        "missing_fields",
    )


class TestFormatPydanticValidationErrorForAgent:
    """Tests for format_pydantic_validation_error_for_agent function."""

    @pytest.mark.parametrize(
        ("input_data", "expected_category"),
        [
            TestData.MISSING_FIELD,
            TestData.EXTRA_FIELD,
            TestData.LARGE_INPUT,
            TestData.MULTIPLE_ERRORS,
        ],
        ids=["missing_field", "extra_field", "large_input", "multiple_errors"],
    )
    def test_structured_details(self, input_data: dict[str, Any], expected_category: str) -> None:
        """Test that structured details contain expected fields and categories."""
        with pytest.raises(ValidationError) as exc_info:
            _SimpleModel.model_validate(input_data)

        message, details = format_pydantic_validation_error_for_agent(exc_info.value)

        # Structure checks
        assert details["model"] == "_SimpleModel"
        assert details["error_count"] >= 1
        assert expected_category in details["categories"]
        assert len(details["errors"]) == details["error_count"]

        # Message checks
        assert "Validation failed for _SimpleModel" in message
        assert str(details["error_count"]) in message

        # Every error has required keys
        for error in details["errors"]:
            assert "field_path" in error
            assert "error_type" in error
            assert "message" in error
            assert "input_value" in error
            assert "context" in error

    def test_large_input_value_not_truncated(self) -> None:
        """Test that large input values are NOT truncated (key improvement over raw pydantic)."""
        large_value = "B" * 500

        class _ModelWithInt(BaseModel):
            value: int

        with pytest.raises(ValidationError) as exc_info:
            _ModelWithInt.model_validate({"value": large_value})

        _message, details = format_pydantic_validation_error_for_agent(exc_info.value)

        # The per-error input_value should contain the full large string, not truncated
        error = details["errors"][0]
        assert isinstance(error["input_value"], str)
        assert len(error["input_value"]) == 500
        assert error["input_value"] == large_value

    def test_literal_error_with_context(self) -> None:
        """Test that literal errors include expected values in context."""
        with pytest.raises(ValidationError) as exc_info:
            _LiteralModel.model_validate({"tone": "InvalidTone"})

        message, details = format_pydantic_validation_error_for_agent(exc_info.value)

        assert details["model"] == "_LiteralModel"
        assert "literal_errors" in details["categories"]
        assert details["error_count"] == 1

        error = details["errors"][0]
        assert error["field_path"] == "tone"
        assert error["error_type"] == "literal_error"
        assert error["input_value"] == "InvalidTone"
        assert "expected" in error["context"]
        assert "literal" in message.lower()

    def test_non_serializable_input_falls_back_to_repr(self) -> None:
        """Test that non-JSON-serializable input values fall back to repr() without crashing."""

        class _ModelWithAny(BaseModel):
            model_config = ConfigDict(extra="forbid")
            value: int

        non_serializable = _NonSerializable()
        with pytest.raises(ValidationError) as exc_info:
            _ModelWithAny.model_validate({"value": non_serializable})

        message, details = format_pydantic_validation_error_for_agent(exc_info.value)

        assert details["error_count"] >= 1
        # The non-serializable input should be represented as its repr string
        error = details["errors"][0]
        assert isinstance(error["input_value"], str)
        assert "NonSerializable" in error["input_value"]
        assert "Validation failed" in message

    def test_context_with_non_serializable_values_is_json_safe(self) -> None:
        """Test that context values containing non-JSON-serializable objects are serialized safely."""

        class _ConstrainedModel(BaseModel):
            score: int = Field(..., ge=10)

        with pytest.raises(ValidationError) as exc_info:
            _ConstrainedModel.model_validate({"score": 5})

        _message, details = format_pydantic_validation_error_for_agent(exc_info.value)

        # The entire details dict must be JSON-serializable (no TypeError)
        serialized = json.dumps(details)
        assert isinstance(serialized, str)

        # Context should contain the 'ge' constraint value, serialized
        error = details["errors"][0]
        assert "context" in error
        assert isinstance(error["context"], dict)

    def test_multiple_errors_all_reported(self) -> None:
        """Test that all errors are reported with correct error_count."""
        with pytest.raises(ValidationError) as exc_info:
            _SimpleModel.model_validate({"unknown_field": "x"})

        message, details = format_pydantic_validation_error_for_agent(exc_info.value)

        # Should have at least 3 errors: missing 'name', missing 'age', extra 'unknown_field'
        assert details["error_count"] >= 3
        assert len(details["errors"]) == details["error_count"]
        assert "missing_fields" in details["categories"]
        assert "extra_fields" in details["categories"]
        assert "errors" in message.lower()
