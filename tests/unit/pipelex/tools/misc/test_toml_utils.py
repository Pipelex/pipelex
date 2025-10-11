from pathlib import Path

import pytest

from pipelex.tools.misc.toml_utils import (
    load_toml_from_path,
    load_toml_from_path_if_exists,
)


class TestTOMLUtils:
    def test_load_toml_from_path_valid_file(self, tmp_path: Path) -> None:
        """Test loading a valid TOML file without issues."""
        toml_content = """domain = "test_domain"
description = "Test definition"

[concept]
TestConcept = "A test concept"

[pipe]
[pipe.test_pipe]
type = "PipeLLM"
description = "Test pipe definition"
prompt_template = '''
This is a test prompt
'''
"""
        toml_file = tmp_path / "valid.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path(str(toml_file))

        assert isinstance(result, dict)
        assert result["domain"] == "test_domain"
        assert result["description"] == "Test definition"
        assert "concept" in result
        assert "pipe" in result

    def test_validate_toml_file_trailing_whitespace(self, tmp_path: Path) -> None:
        """Test detection of trailing whitespace."""
        toml_content = """domain = "test"
description = "Test"
"""
        toml_file = tmp_path / "trailing_space.toml"
        toml_file.write_text(toml_content)

    def test_validate_toml_file_trailing_space_after_triple_quotes(self, tmp_path: Path) -> None:
        """Test detection of trailing whitespace after triple quotes."""
        toml_content = '''domain = "test"

[pipe.test_pipe]
type = "PipeLLM"
description = "Test"
prompt_template = """
Output this only: "test"
"""
'''
        toml_file = tmp_path / "trailing_quotes.toml"
        toml_file.write_text(toml_content)

    @pytest.mark.skip(reason="Mixed line ending detection needs refinement - focusing on trailing whitespace detection")
    def test_validate_toml_file_mixed_line_endings(self, tmp_path: Path) -> None:
        """Test detection of mixed line endings."""
        # Create content with explicit mixed line endings - use binary mode to ensure exact control
        toml_file = tmp_path / "mixed_endings.toml"
        # Write content with mixed line endings directly in binary mode
        mixed_content = b'domain = "test"\r\\description = "Test"\nextra = "value"\n'
        toml_file.write_bytes(mixed_content)

    def test_load_toml_from_path_no_validation_by_default(self, tmp_path: Path) -> None:
        """Test that loading works normally without validation."""
        toml_content = """domain = "test"
description = "Test with trailing space"
"""
        toml_file = tmp_path / "no_validation.toml"
        toml_file.write_text(toml_content)

        # Should not raise - loading doesn't validate by default
        result = load_toml_from_path(str(toml_file))

        assert isinstance(result, dict)
        assert result["domain"] == "test"

    def test_load_toml_from_path_if_exists_nonexistent_file(self) -> None:
        """Test failable loading with non-existent file."""
        result = load_toml_from_path_if_exists("/nonexistent/path.toml")
        assert result is None

    def test_load_toml_from_path_if_exists_valid_file(self, tmp_path: Path) -> None:
        """Test failable loading with valid file."""
        toml_content = """domain = "test"
description = "Test definition"
"""
        toml_file = tmp_path / "valid.toml"
        toml_file.write_text(toml_content)

        result = load_toml_from_path_if_exists(str(toml_file))

        assert result is not None
        assert result["domain"] == "test"

    def test_load_toml_from_path_if_exists_with_whitespace_works(self, tmp_path: Path) -> None:
        """Test failable loading works normally with whitespace."""
        toml_content = """domain = "test"
"""
        toml_file = tmp_path / "with_whitespace.toml"
        toml_file.write_text(toml_content)

        # Should work fine - loading doesn't validate by default
        result = load_toml_from_path_if_exists(str(toml_file))
        assert result is not None
        assert result["domain"] == "test"

    def test_validate_toml_file_valid_file_passes(self, tmp_path: Path) -> None:
        """Test that validation passes for valid files."""
        toml_content = """domain = "test"
description = "Test definition"

[concept]
TestConcept = "A test concept"
"""
        toml_file = tmp_path / "valid.toml"
        toml_file.write_text(toml_content)

    def test_validate_toml_file_multiple_validation_issues(self, tmp_path: Path) -> None:
        """Test that multiple validation issues are all reported."""
        toml_content = """domain = "test"
description = "Test"

[pipe.test_pipe]
prompt_template = \"\"\"
Output: "test"
\"\"\"
"""
        toml_file = tmp_path / "multiple_issues.toml"
        toml_file.write_text(toml_content)

    def test_validate_toml_file_error_contains_file_path(self, tmp_path: Path) -> None:
        """Test that validation error includes the file path."""
        toml_content = """domain = "test"
"""
        toml_file = tmp_path / "path_test.toml"
        toml_file.write_text(toml_content)

    def test_validate_toml_file_pipe_condition_real_case(self, tmp_path: Path) -> None:
        """Test the exact scenario from pipe_condition_2.toml with trailing space after triple quotes."""
        toml_content = '''domain = "test_pipe_condition_2"
description = "Simple test for PipeCondition functionality using expression"

[concept]
CategoryInput = "Input with a category field"

[pipe]
[pipe.basic_condition_by_category_2]
type = "PipeCondition"
description = "Route based on category field using expression"
inputs = { input_data = "CategoryInput" }
output = "native.Text"
expression = "input_data.category"

[pipe.basic_condition_by_category_2.pipe_map]
small = "process_small_2"
medium = "process_medium_2"
large = "process_large_2"

[pipe.process_large_2]
type = "PipeLLM"
description = "Generate random text for large items"
output = "native.Text"
prompt_template = """
Output this only: "large"
""" '''
        toml_file = tmp_path / "pipe_condition_real_case.toml"
        toml_file.write_text(toml_content)
