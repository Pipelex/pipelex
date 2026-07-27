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
