from pathlib import Path

import pytest

from pipelex import pretty_print
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter import PipelexInterpreter
from tests.unit.pipelex.core.test_data import InterpreterTestCases


class TestPipelexInterpreter:
    def test_init_with_both_file_path_and_content(self, tmp_path: Path):
        test_file = tmp_path / "test.plx"
        test_file.write_text("domain = 'test'\n[concept]\n")
        content = "domain = 'other'\n[concept]\n"

        converter = PipelexInterpreter(file_path=test_file, file_content=content)
        assert converter.file_path == test_file
        assert converter.file_content == content

    @pytest.mark.parametrize("test_name,plx_content,expected_blueprint", InterpreterTestCases.VALID_TEST_CASES)
    def test_make_pipelex_bundle_blueprint(self, test_name: str, plx_content: str, expected_blueprint: PipelexBundleBlueprint):
        converter = PipelexInterpreter(file_content=plx_content)


        blueprint = converter.make_pipelex_bundle_blueprint()
        pretty_print(blueprint, title=f"Blueprint {test_name}")
        pretty_print(expected_blueprint, title=f"Expected blueprint {test_name}")
        assert blueprint == expected_blueprint

    @pytest.mark.parametrize("test_name,plx_content,expected_blueprint", InterpreterTestCases.VALID_TEST_CASES)
    def test_make_plx_content(self, test_name: str, plx_content: str, expected_blueprint: PipelexBundleBlueprint):
        get_plx_content = PipelexInterpreter.make_plx_content(blueprint=expected_blueprint)

        pretty_print(get_plx_content, title=f"PLx content {test_name}")
        pretty_print(plx_content, title=f"Expected PLX content {test_name}")
        assert get_plx_content == plx_content

    @pytest.mark.parametrize("test_name,invalid_plx_content,expected_exception", InterpreterTestCases.ERROR_TEST_CASES)
    def test_invalid_plx_should_raise_exception(self, test_name: str, invalid_plx_content: str, expected_exception: type[Exception]):
        converter = PipelexInterpreter(file_content=invalid_plx_content)

        with pytest.raises(expected_exception):
            converter.make_pipelex_bundle_blueprint()
