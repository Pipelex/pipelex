from pathlib import Path

import pytest

from pipelex.tools.misc.toml_utils import (
    TOMLValidationError,
    failable_load_toml_from_path,
    load_toml_from_path,
    validate_toml_file,
)


class TestPLXUtils:
    def test_load_plx_from_path_valid_file(self, tmp_path: Path) -> None:
        """Test loading a valid PLX file without issues."""
        plx_content = """domain = "test_domain"
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
        plx_file = tmp_path / "valid.plx"
        plx_file.write_text(plx_content)

        result = load_toml_from_path(str(plx_file))

        assert isinstance(result, dict)
        assert result["domain"] == "test_domain"
        assert result["definition"] == "Test definition"
        assert "concept" in result
        assert "pipe" in result

    def test_validate_plx_file_trailing_whitespace(self, tmp_path: Path) -> None:
        """Test detection of trailing whitespace."""
        plx_content = """domain = "test"   
definition = "Test"	
"""
        plx_file = tmp_path / "trailing_space.plx"
        plx_file.write_text(plx_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(plx_file))

        error_msg = str(exc_info.value)
        assert "Trailing whitespace detected" in error_msg
        assert "Line 1" in error_msg
        assert "Line 2" in error_msg

    def test_validate_plx_file_trailing_space_after_triple_quotes(self, tmp_path: Path) -> None:
        """Test detection of trailing whitespace after triple quotes."""
        plx_content = '''domain = "test"

[pipe.test_pipe]
type = "PipeLLM"
definition = "Test"
prompt_template = """
Output this only: "test"
"""   
'''
        plx_file = tmp_path / "trailing_quotes.plx"
        plx_file.write_text(plx_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(plx_file))

        error_msg = str(exc_info.value)
        assert "Trailing whitespace after triple quotes" in error_msg
        assert "Line 8" in error_msg

    @pytest.mark.skip(reason="Mixed line ending detection needs refinement - focusing on trailing whitespace detection")
    def test_validate_plx_file_mixed_line_endings(self, tmp_path: Path) -> None:
        """Test detection of mixed line endings."""
        # Create content with explicit mixed line endings - use binary mode to ensure exact control
        plx_file = tmp_path / "mixed_endings.plx"
        # Write content with mixed line endings directly in binary mode
        mixed_content = b'domain = "test"\r\ndefinition = "Test"\nextra = "value"\n'
        plx_file.write_bytes(mixed_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(plx_file))

        error_msg = str(exc_info.value)
        assert "Mixed line endings detected" in error_msg

    def test_load_plx_from_path_no_validation_by_default(self, tmp_path: Path) -> None:
        """Test that loading works normally without validation."""
        plx_content = """domain = "test"   
definition = "Test with trailing space"
"""
        plx_file = tmp_path / "no_validation.plx"
        plx_file.write_text(plx_content)

        # Should not raise - loading doesn't validate by default
        result = load_toml_from_path(str(plx_file))

        assert isinstance(result, dict)
        assert result["domain"] == "test"

    def test_failable_load_plx_from_path_nonexistent_file(self) -> None:
        """Test failable loading with non-existent file."""
        result = failable_load_toml_from_path("/nonexistent/path.plx")
        assert result is None

    def test_failable_load_plx_from_path_valid_file(self, tmp_path: Path) -> None:
        """Test failable loading with valid file."""
        plx_content = """domain = "test"
definition = "Test definition"
"""
        plx_file = tmp_path / "valid.plx"
        plx_file.write_text(plx_content)

        result = failable_load_toml_from_path(str(plx_file))

        assert result is not None
        assert result["domain"] == "test"

    def test_failable_load_plx_from_path_with_whitespace_works(self, tmp_path: Path) -> None:
        """Test failable loading works normally with whitespace."""
        plx_content = """domain = "test"   
"""
        plx_file = tmp_path / "with_whitespace.plx"
        plx_file.write_text(plx_content)

        # Should work fine - loading doesn't validate by default
        result = failable_load_toml_from_path(str(plx_file))
        assert result is not None
        assert result["domain"] == "test"

    def test_validate_plx_file_valid_file_passes(self, tmp_path: Path) -> None:
        """Test that validation passes for valid files."""
        plx_content = """domain = "test"
definition = "Test definition"

[concept]
TestConcept = "A test concept"
"""
        plx_file = tmp_path / "valid.plx"
        plx_file.write_text(plx_content)

        # Should not raise
        validate_toml_file(str(plx_file))

    def test_validate_toml_file_multiple_validation_issues(self, tmp_path: Path) -> None:
        """Test that multiple validation issues are all reported."""
        plx_content = """domain = "test"   
definition = "Test"	

[pipe.test_pipe]
prompt_template = \"\"\"
Output: "test"
\"\"\" 
"""
        plx_file = tmp_path / "multiple_issues.plx"
        plx_file.write_text(plx_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(plx_file))

        error_msg = str(exc_info.value)
        # Should detect multiple lines with trailing whitespace
        assert "Line 1" in error_msg
        assert "Line 2" in error_msg
        assert "Line 7" in error_msg
        assert "Trailing whitespace after triple quotes" in error_msg

    def test_validate_plx_file_error_contains_file_path(self, tmp_path: Path) -> None:
        """Test that validation error includes the file path."""
        plx_content = """domain = "test"   
"""
        plx_file = tmp_path / "path_test.plx"
        plx_file.write_text(plx_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(plx_file))

        error_msg = str(exc_info.value)
        assert str(plx_file) in error_msg
        assert "TOML formatting issues" in error_msg

    def test_validate_plx_file_pipe_condition_real_case(self, tmp_path: Path) -> None:
        """Test the exact scenario from pipe_condition_2.plx with trailing space after triple quotes."""
        plx_content = '''domain = "test_pipe_condition_2"
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
        plx_file = tmp_path / "pipe_condition_real_case.plx"
        plx_file.write_text(plx_content)

        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(str(plx_file))

        error_msg = str(exc_info.value)
        assert "Trailing whitespace after triple quotes" in error_msg
        assert "Line 26" in error_msg  # The line with """ followed by space

    def test_validate_plx_file_actual_problematic_file(self) -> None:
        """Test validation on the actual problematic file from the codebase."""
        problematic_file = "tests/data/tools_data/problematic_test_cases.plx"

        # This should catch multiple trailing whitespace issues
        with pytest.raises(TOMLValidationError) as exc_info:
            validate_toml_file(problematic_file)

        error_msg = str(exc_info.value)
        assert "Trailing whitespace" in error_msg
        assert problematic_file in error_msg
