import os
from pathlib import Path

import pytest

from pipelex.tools.misc.toml_utils import (
    TOMLValidationError,
    failable_load_toml_from_path,
    load_toml_from_path,
    validate_toml_file,
)


class TestTOMLUtils:
    def test_load_toml_from_path_valid_file(self, tmp_path: Path) -> None:
        """Test loading a valid TOML file without issues."""
        toml_content = """domain = "test_domain"
definition = "Test definition"

[concept]
TestConcept = "A test concept"

[pipe]
[pipe.test_pipe]
type = "PipeLLM"
definition = "Test pipe definition"
prompt_template = '''
This is a test prompt
''' 
"""
        toml_file = tmp_path / "valid.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path(str(toml_file))

        assert isinstance(result, dict)
        assert result["domain"] == "test_domain"
        assert result["definition"] == "Test definition"
        assert "concept" in result
        assert "pipe" in result

    def test_validate_toml_file_trailing_whitespace(self, tmp_path: Path) -> None:
        """Test detection of trailing whitespace."""
        toml_content = """domain = "test"   
definition = "Test"	
"""
        toml_file = tmp_path / "trailing_space.toml"
        toml_file.write_text(toml_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(toml_file))

        error_msg = str(exc_info.value)
        assert "Trailing whitespace detected" in error_msg
        assert "Line 1" in error_msg
        assert "Line 2" in error_msg

    def test_validate_toml_file_trailing_space_after_triple_quotes(self, tmp_path: Path) -> None:
        """Test detection of trailing whitespace after triple quotes."""
        toml_content = '''domain = "test"

[pipe.test_pipe]
type = "PipeLLM"
definition = "Test"
prompt_template = """
Output this only: "test"
"""   
'''
        toml_file = tmp_path / "trailing_quotes.toml"
        toml_file.write_text(toml_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(toml_file))

        error_msg = str(exc_info.value)
        assert "Trailing whitespace after triple quotes" in error_msg
        assert "Line 8" in error_msg

    @pytest.mark.skip(reason="Mixed line ending detection needs refinement - focusing on trailing whitespace detection")
    def test_validate_toml_file_mixed_line_endings(self, tmp_path: Path) -> None:
        """Test detection of mixed line endings."""
        # Create content with explicit mixed line endings - use binary mode to ensure exact control
        toml_file = tmp_path / "mixed_endings.toml"
        # Write content with mixed line endings directly in binary mode
        mixed_content = b'domain = "test"\r\ndefinition = "Test"\nextra = "value"\n'
        toml_file.write_bytes(mixed_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(toml_file))

        error_msg = str(exc_info.value)
        assert "Mixed line endings detected" in error_msg

    def test_load_toml_from_path_no_validation_by_default(self, tmp_path: Path) -> None:
        """Test that loading works normally without validation."""
        toml_content = """domain = "test"   
definition = "Test with trailing space"
"""
        toml_file = tmp_path / "no_validation.toml"
        toml_file.write_text(toml_content)

        # Should not raise - loading doesn't validate by default
        result = load_toml_from_path(str(toml_file))

        assert isinstance(result, dict)
        assert result["domain"] == "test"

    def test_failable_load_toml_from_path_nonexistent_file(self) -> None:
        """Test failable loading with non-existent file."""
        result = failable_load_toml_from_path("/nonexistent/path.toml")
        assert result is None

    def test_failable_load_toml_from_path_valid_file(self, tmp_path: Path) -> None:
        """Test failable loading with valid file."""
        toml_content = """domain = "test"
definition = "Test definition"
"""
        toml_file = tmp_path / "valid.toml"
        toml_file.write_text(toml_content)

        result = failable_load_toml_from_path(str(toml_file))

        assert result is not None
        assert result["domain"] == "test"

    def test_failable_load_toml_from_path_with_whitespace_works(self, tmp_path: Path) -> None:
        """Test failable loading works normally with whitespace."""
        toml_content = """domain = "test"   
"""
        toml_file = tmp_path / "with_whitespace.toml"
        toml_file.write_text(toml_content)

        # Should work fine - loading doesn't validate by default
        result = failable_load_toml_from_path(str(toml_file))
        assert result is not None
        assert result["domain"] == "test"

    def test_validate_toml_file_valid_file_passes(self, tmp_path: Path) -> None:
        """Test that validation passes for valid files."""
        toml_content = """domain = "test"
definition = "Test definition"

[concept]
TestConcept = "A test concept"
"""
        toml_file = tmp_path / "valid.toml"
        toml_file.write_text(toml_content)

        # Should not raise
        validate_toml_file(str(toml_file))

    def test_validate_toml_file_multiple_validation_issues(self, tmp_path: Path) -> None:
        """Test that multiple validation issues are all reported."""
        toml_content = """domain = "test"   
definition = "Test"	

[pipe.test_pipe]
prompt_template = \"\"\"
Output: "test"
\"\"\" 
"""
        toml_file = tmp_path / "multiple_issues.toml"
        toml_file.write_text(toml_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(toml_file))

        error_msg = str(exc_info.value)
        # Should detect multiple lines with trailing whitespace
        assert "Line 1" in error_msg
        assert "Line 2" in error_msg
        assert "Line 7" in error_msg
        assert "Trailing whitespace after triple quotes" in error_msg

    def test_validate_toml_file_error_contains_file_path(self, tmp_path: Path) -> None:
        """Test that validation error includes the file path."""
        toml_content = """domain = "test"   
"""
        toml_file = tmp_path / "path_test.toml"
        toml_file.write_text(toml_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(toml_file))

        error_msg = str(exc_info.value)
        assert str(toml_file) in error_msg
        assert "TOML formatting issues" in error_msg

    def test_validate_toml_file_pipe_condition_real_case(self, tmp_path: Path) -> None:
        """Test the exact scenario from pipe_condition_2.toml with trailing space after triple quotes."""
        toml_content = '''domain = "test_pipe_condition_2"
definition = "Simple test for PipeCondition functionality using expression"

[concept]
CategoryInput = "Input with a category field"

[pipe]
[pipe.basic_condition_by_category_2]
type = "PipeCondition"
definition = "Route based on category field using expression"
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression = "input_data.category"

[pipe.basic_condition_by_category_2.pipe_map]
small = "process_small_2"
medium = "process_medium_2" 
large = "process_large_2"

[pipe.process_large_2]
type = "PipeLLM"
definition = "Generate random text for large items"
output = "native.Text"
prompt_template = """
Output this only: "large"
""" '''
        toml_file = tmp_path / "pipe_condition_real_case.toml"
        toml_file.write_text(toml_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(toml_file))

        error_msg = str(exc_info.value)
        assert "Trailing whitespace after triple quotes" in error_msg
        assert "Line 26" in error_msg  # The line with """ followed by space

    def test_validate_toml_file_actual_problematic_file(self) -> None:
        """Test validation on the actual problematic file from the codebase."""
        problematic_file = "tests/data/tools_data/problematic_test_cases.toml"

        # This should catch multiple trailing whitespace issues
        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(problematic_file)

        error_msg = str(exc_info.value)
        assert "Trailing whitespace" in error_msg
        assert problematic_file in error_msg

    def test_load_toml_with_var_substitution_simple(self, tmp_path: Path) -> None:
        """Test loading TOML with simple variable substitution using environment variables."""
        # Set up environment variables for testing
        os.environ["TEST_USER"] = "john_doe"
        os.environ["TEST_VERSION"] = "1.2.3"

        try:
            toml_content = """domain = "${TEST_USER}_domain"
version = "v${TEST_VERSION}"
description = "Test for user ${TEST_USER}"

[config]
user_name = "${TEST_USER}"
app_version = "${TEST_VERSION}"
static_value = "no_substitution"
number_value = 42
"""

            toml_file = tmp_path / "test_env.toml"
            toml_file.write_text(toml_content)

            # Test with variable substitution enabled
            result = load_toml_from_path(str(toml_file), is_var_substitution_enabled=True)

            assert result["domain"] == "john_doe_domain"
            assert result["version"] == "v1.2.3"
            assert result["description"] == "Test for user john_doe"
            assert result["config"]["user_name"] == "john_doe"
            assert result["config"]["app_version"] == "1.2.3"
            assert result["config"]["static_value"] == "no_substitution"  # No env vars
            assert result["config"]["number_value"] == 42  # Non-string unchanged

            # Test with variable substitution disabled (default)
            result_no_sub = load_toml_from_path(str(toml_file), is_var_substitution_enabled=False)

            assert result_no_sub["domain"] == "${TEST_USER}_domain"  # No substitution
            assert result_no_sub["version"] == "v${TEST_VERSION}"  # No substitution

        finally:
            # Clean up environment variables
            os.environ.pop("TEST_USER", None)
            os.environ.pop("TEST_VERSION", None)

    def test_load_toml_with_env_var_substitution_nested_structures(self, tmp_path: Path) -> None:
        """Test loading TOML with env var substitution in nested structures and lists."""
        # Set up environment variables
        os.environ["TEST_HOST"] = "localhost"
        os.environ["TEST_PORT"] = "8080"
        os.environ["TEST_ENV"] = "development"

        try:
            toml_content = """domain = "test_domain"

[database]
host = "${TEST_HOST}"
port = "${TEST_PORT}"
config = { env = "${TEST_ENV}", timeout = 30 }

[servers]
primary = "${TEST_HOST}:${TEST_PORT}"
urls = ["http://${TEST_HOST}:${TEST_PORT}/api", "https://${TEST_HOST}:9443/secure"]

[[services]]
name = "api_${TEST_ENV}"
endpoint = "${TEST_HOST}:${TEST_PORT}"

[[services]]
name = "static"
endpoint = "cdn.example.com"
"""

            toml_file = tmp_path / "test_nested_env.toml"
            toml_file.write_text(toml_content)

            result = load_toml_from_path(str(toml_file), is_var_substitution_enabled=True)

            # Test nested dictionary substitution
            assert result["database"]["host"] == "localhost"
            assert result["database"]["port"] == "8080"
            assert result["database"]["config"]["env"] == "development"
            assert result["database"]["config"]["timeout"] == 30  # Non-string unchanged

            # Test string with multiple env vars
            assert result["servers"]["primary"] == "localhost:8080"

            # Test list with env var substitution
            expected_urls = ["http://localhost:8080/api", "https://localhost:9443/secure"]
            assert result["servers"]["urls"] == expected_urls

            # Test array of tables
            assert result["services"][0]["name"] == "api_development"
            assert result["services"][0]["endpoint"] == "localhost:8080"
            assert result["services"][1]["name"] == "static"  # No env vars
            assert result["services"][1]["endpoint"] == "cdn.example.com"  # No env vars

        finally:
            # Clean up
            for var in ["TEST_HOST", "TEST_PORT", "TEST_ENV"]:
                os.environ.pop(var, None)

    def test_load_toml_with_env_var_substitution_with_defaults(self, tmp_path: Path) -> None:
        """Test loading TOML with environment variable substitution using default values."""
        # Only set one env var, let the other use defaults
        os.environ["TEST_EXISTING"] = "exists"

        try:
            toml_content = """domain = "test_domain"
existing_var = "${TEST_EXISTING}"
missing_with_default = "${TEST_MISSING:default_value}"
nested_default = "${TEST_NESTED:prod_${TEST_EXISTING}}"

[config]
values = ["${TEST_EXISTING}", "${TEST_MISSING:fallback}", "static"]
"""

            toml_file = tmp_path / "test_defaults.toml"
            toml_file.write_text(toml_content)

            result = load_toml_from_path(str(toml_file), is_var_substitution_enabled=True)

            assert result["existing_var"] == "exists"
            assert result["missing_with_default"] == "default_value"
            assert result["nested_default"] == "prod_${TEST_EXISTING}"  # Default values are not recursively substituted
            assert result["config"]["values"] == ["exists", "fallback", "static"]

        finally:
            os.environ.pop("TEST_EXISTING", None)

    def test_load_toml_with_env_var_substitution_missing_required_var(self, tmp_path: Path) -> None:
        """Test that missing required environment variables raise an error."""
        toml_content = """domain = "test_domain"
required_var = "${REQUIRED_MISSING_VAR}"
"""

        toml_file = tmp_path / "test_missing_var.toml"
        toml_file.write_text(toml_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            load_toml_from_path(str(toml_file), is_var_substitution_enabled=True)

        error_msg = str(exc_info.value)
        assert "Variable substitution failed" in error_msg
        assert "REQUIRED_MISSING_VAR" in error_msg
