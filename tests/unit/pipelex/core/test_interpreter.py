from pathlib import Path
from typing import Type

import pytest

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter import PipelexInterpreter
from tests.unit.pipelex.core.test_data import InterpreterTestCases


class TestPipelexInterpreter:
    """Test the PipelexInterpreter class with various TOML configurations."""

    def test_init_with_both_file_path_and_content(self, tmp_path: Path):
        """Test initialization with both file_path and file_content."""
        test_file = tmp_path / "test.toml"
        test_file.write_text("domain = 'test'\n[concept]\n")
        content = "domain = 'other'\n[concept]\n"

        converter = PipelexInterpreter(file_path=test_file, file_content=content)
        assert converter.file_path == test_file
        assert converter.file_content == content

    @pytest.mark.parametrize("test_name,toml_content,expected_blueprint", InterpreterTestCases.VALID_TEST_CASES)
    def test_make_pipelex_bundle_blueprint(self, test_name: str, toml_content: str, expected_blueprint: PipelexBundleBlueprint):
        """Test making blueprint from various valid TOML content."""
        converter = PipelexInterpreter(file_content=toml_content)
        from pipelex import pretty_print

        blueprint = converter.make_pipelex_bundle_blueprint()
        pretty_print(blueprint, title=f"Blueprint {test_name}")
        pretty_print(expected_blueprint, title=f"Expected blueprint {test_name}")
        assert blueprint == expected_blueprint

    @pytest.mark.parametrize("test_name,toml_content,expected_blueprint", InterpreterTestCases.VALID_TEST_CASES)
    def test_make_toml_content(self, test_name: str, toml_content: str, expected_blueprint: PipelexBundleBlueprint):
        """Test making blueprint from various valid TOML content."""
        get_toml_content = PipelexInterpreter.make_toml_content(blueprint=expected_blueprint)
        from pipelex import pretty_print

        pretty_print(get_toml_content, title=f"TOML content {test_name}")
        pretty_print(toml_content, title=f"Expected TOML content {test_name}")
        assert get_toml_content == toml_content

    @pytest.mark.parametrize("test_name,invalid_toml_content,expected_exception", InterpreterTestCases.ERROR_TEST_CASES)
    def test_invalid_toml_should_raise_exception(self, test_name: str, invalid_toml_content: str, expected_exception: Type[Exception]):
        """Test that invalid TOML content raises appropriate exceptions."""
        converter = PipelexInterpreter(file_content=invalid_toml_content)

        with pytest.raises(expected_exception):
            converter.make_pipelex_bundle_blueprint()
