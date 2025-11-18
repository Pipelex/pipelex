import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


class TestFormatPydanticValidationError:
    """Tests for format_pydantic_validation_error function."""

    def test_single_missing_and_extra_field(self) -> None:
        """Test formatting with a single missing and extra field."""

        class Validated(BaseModel):
            model_config = ConfigDict(extra="forbid")
            a: int
            b: str

        with pytest.raises(ValidationError) as exc:
            Validated.model_validate({"a": "not_int", "c": 1})

        formatted = format_pydantic_validation_error(exc.value)
        assert "Missing required fields: 'b'" in formatted
        assert "Extra forbidden fields: 'c'" in formatted

    def test_multiple_missing_fields(self) -> None:
        """Test formatting with multiple missing required fields displayed as comma-separated list."""

        class MultiRequired(BaseModel):
            model_config = ConfigDict(extra="forbid")
            field1: str
            field2: int
            field3: bool

        with pytest.raises(ValidationError) as exc:
            MultiRequired.model_validate({})

        formatted = format_pydantic_validation_error(exc.value)
        assert "Missing required fields:" in formatted
        assert "'field1'" in formatted
        assert "'field2'" in formatted
        assert "'field3'" in formatted
        # Check comma separation (order may vary)
        assert ", " in formatted

    def test_multiple_extra_fields(self) -> None:
        """Test formatting with multiple extra forbidden fields displayed as comma-separated list."""

        class NoExtras(BaseModel):
            model_config = ConfigDict(extra="forbid")
            valid_field: str

        with pytest.raises(ValidationError) as exc:
            NoExtras.model_validate({"valid_field": "ok", "extra1": 1, "extra2": 2, "extra3": 3})

        formatted = format_pydantic_validation_error(exc.value)
        assert "Extra forbidden fields:" in formatted
        assert "'extra1'" in formatted
        assert "'extra2'" in formatted
        assert "'extra3'" in formatted
        # Check comma separation
        assert ", " in formatted

    def test_combination_of_multiple_missing_and_extra_fields(self) -> None:
        """Test formatting with both multiple missing and extra fields together."""

        class MultiRequired(BaseModel):
            model_config = ConfigDict(extra="forbid")
            field1: str
            field2: int
            field3: bool

        with pytest.raises(ValidationError) as exc:
            MultiRequired.model_validate({"wrong1": "a", "wrong2": "b"})

        formatted = format_pydantic_validation_error(exc.value)
        assert "Missing required fields:" in formatted
        assert "Extra forbidden fields:" in formatted
        # Check for at least one missing field
        assert "'field1'" in formatted or "'field2'" in formatted or "'field3'" in formatted
        # Check for extra fields
        assert "'wrong1'" in formatted
        assert "'wrong2'" in formatted

    def test_model_type_errors(self) -> None:
        """Test formatting with model type validation errors."""

        class InnerModel(BaseModel):
            value: int

        class OuterModel(BaseModel):
            inner: InnerModel

        with pytest.raises(ValidationError) as exc:
            OuterModel.model_validate({"inner": "not_a_model"})

        formatted = format_pydantic_validation_error(exc.value)
        assert "Model type errors:" in formatted
        assert "expected InnerModel, got str" in formatted
