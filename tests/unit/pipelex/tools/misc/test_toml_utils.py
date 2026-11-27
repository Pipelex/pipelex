from pathlib import Path

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
user_prompt = '''
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
