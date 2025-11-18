import pytest

from pipelex.core.pipes.exceptions import PipeBlueprintValueError
from pipelex.core.pipes.validation import is_valid_input_name, validate_input_name


class TestInputNameValidation:
    """Test input name validation functions."""

    @pytest.mark.parametrize(
        ("input_name", "expected_result"),
        [
            # Valid cases
            ("my_input", True),
            ("input_123", True),
            ("my_input_field", True),
            ("my_input.field_name", True),
            ("my_input.field_name.nested_field", True),
            ("input_1.field_2.nested_3", True),
            ("a", True),
            ("a_b", True),
            ("a.b", True),
            ("a.b.c", True),
            # Invalid cases - not snake_case
            ("myInput", False),
            ("MyInput", False),
            ("my-input", False),
            ("my input", False),
            ("123_input", False),  # Cannot start with number
            # Invalid cases - dot issues
            ("", False),
            (".", False),
            (".my_input", False),
            ("my_input.", False),
            ("my_input..field", False),
            ("my_input...field", False),
            ("..", False),
            ("...", False),
            # Invalid cases - mixed with valid dots
            ("my_input.fieldName", False),  # Second part not snake_case
            ("myInput.field_name", False),  # First part not snake_case
            ("my_input.Field_name", False),  # Second part starts with uppercase
            ("my_input..field_name", False),  # Consecutive dots
            ("my_input.field_name.", False),  # Trailing dot
            (".my_input.field_name", False),  # Leading dot
        ],
    )
    def test_is_valid_input_name(self, input_name: str, expected_result: bool):
        """Test is_valid_input_name with various input names."""
        assert is_valid_input_name(input_name) == expected_result

    @pytest.mark.parametrize(
        "valid_input_name",
        [
            "my_input",
            "input_123",
            "my_input_field",
            "my_input.field_name",
            "my_input.field_name.nested_field",
            "input_1.field_2.nested_3",
            "a",
            "a_b",
            "a.b",
            "a.b.c",
        ],
    )
    def test_validate_input_name_valid(self, valid_input_name: str):
        """Test validate_input_name does not raise for valid input names."""
        validate_input_name(valid_input_name)  # Should not raise

    @pytest.mark.parametrize(
        "invalid_input_name",
        [
            "myInput",
            "MyInput",
            "my-input",
            "my input",
            "123_input",
            "",
            ".",
            ".my_input",
            "my_input.",
            "my_input..field",
            "my_input...field",
            "..",
            "...",
            "my_input.fieldName",
            "myInput.field_name",
            "my_input.Field_name",
        ],
    )
    def test_validate_input_name_invalid(self, invalid_input_name: str):
        """Test validate_input_name raises PipeBlueprintValueError for invalid input names."""
        with pytest.raises(PipeBlueprintValueError, match="Invalid input name syntax"):
            validate_input_name(invalid_input_name)

    def test_validate_input_name_error_message(self):
        """Test that the error message is helpful and descriptive."""
        with pytest.raises(PipeBlueprintValueError) as exc_info:
            validate_input_name("myInput.fieldName")

        error_message = str(exc_info.value)
        assert "Invalid input name syntax 'myInput.fieldName'" in error_message
        assert "snake_case" in error_message
        assert "dots" in error_message or "nested field" in error_message.lower()
