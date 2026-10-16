from pathlib import Path

import pytest

from pipelex import log, pretty_print
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from tests.unit.pipelex.core.test_data import InterpreterTestCases


class TestMthdsParser:
    @pytest.mark.parametrize(("test_name", "mthds_content", "expected_blueprint"), InterpreterTestCases.VALID_TEST_CASES)
    def test_make_pipelex_bundle_blueprint(self, test_name: str, mthds_content: str, expected_blueprint: PipelexBundleBlueprint):
        """Test making blueprint from various valid MTHDS content."""
        blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content)

        pretty_print(blueprint, title=f"Blueprint {test_name}")
        pretty_print(expected_blueprint, title=f"Expected blueprint {test_name}")
        assert blueprint == expected_blueprint

    @pytest.mark.parametrize(("test_name", "invalid_mthds_content", "expected_exception"), InterpreterTestCases.ERROR_TEST_CASES)
    def test_invalid_mthds_should_raise_exception(self, test_name: str, invalid_mthds_content: str, expected_exception: type[Exception]):
        """Test that invalid MTHDS content raises appropriate exceptions."""
        log.verbose(f"Testing invalid MTHDS content: {test_name}")
        with pytest.raises(expected_exception):
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=invalid_mthds_content)

    def test_toml_syntax_error_carries_mthds_source(self):
        """Parse-level errors must still expose the caller-supplied logical source."""
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(
                mthds_content='domain = "broken" trailing',
                mthds_source="broken.mthds",
            )

        err = exc_info.value
        assert err.validation_errors is not None
        assert len(err.validation_errors) == 1
        assert err.validation_errors[0].source == "broken.mthds"
        assert "TOML syntax error" in err.validation_errors[0].message

    def test_a_bundle_read_from_a_path_is_named_by_its_source_when_given(self, tmp_path: Path):
        """A host reading a tree it wrote out names each bundle by its tree path, never by the file it wrote."""
        bundle_path = tmp_path / "written" / "methods" / "greet.mthds"
        bundle_path.parent.mkdir(parents=True)
        bundle_path.write_text('domain = "greeting"\n', encoding="utf-8")

        blueprint = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=bundle_path, mthds_source="methods/greet.mthds")

        assert blueprint.source == "methods/greet.mthds"

    def test_a_toml_error_of_a_bundle_read_from_a_path_names_its_source_not_the_path(self, tmp_path: Path):
        bundle_path = tmp_path / "written" / "methods" / "broken.mthds"
        bundle_path.parent.mkdir(parents=True)
        bundle_path.write_text('domain = "broken"\n[pipe.oops\n', encoding="utf-8")

        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(bundle_path=bundle_path, mthds_source="methods/broken.mthds")

        (item,) = exc_info.value.validation_errors or []
        assert item.source == "methods/broken.mthds"
        assert "'methods/broken.mthds'" in item.message
        assert str(tmp_path) not in item.message
        assert str(tmp_path) not in exc_info.value.message
