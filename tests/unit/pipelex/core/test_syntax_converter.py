from pathlib import Path

import pytest

from pipelex.core.bundle.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.syntax_converter import PipelexSyntaxConverter
from tests.unit.pipelex.core.syntax_converter_test_data import SyntaxConverterTestCases


class TestPipelexSyntaxConverter:
    """Test the PipelexSyntaxConverter class with various TOML configurations."""

    def test_init_with_both_file_path_and_content(self, tmp_path: Path):
        """Test initialization with both file_path and file_content."""
        test_file = tmp_path / "test.toml"
        test_file.write_text("domain = 'test'\n[concepts]\n")
        content = "domain = 'other'\n[concepts]\n"

        converter = PipelexSyntaxConverter(file_path=test_file, file_content=content)
        assert converter.file_path == test_file
        assert converter.file_content == content

    @pytest.mark.parametrize("test_name,toml_content,expected_blueprint", SyntaxConverterTestCases.VALID_TEST_CASES)
    def test_make_pipelex_bundle_blueprint(self, test_name: str, toml_content: str, expected_blueprint: PipelexBundleBlueprint):
        """Test making blueprint from various valid TOML content."""
        converter = PipelexSyntaxConverter(file_content=toml_content)

        blueprint = converter.make_pipelex_bundle_blueprint()
        assert blueprint == expected_blueprint
