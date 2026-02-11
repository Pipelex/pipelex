import pytest

from pipelex import log, pretty_print
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from tests.unit.pipelex.core.test_data import InterpreterTestCases


class TestPipelexInterpreter:
    @pytest.mark.parametrize(("test_name", "mthds_content", "expected_blueprint"), InterpreterTestCases.VALID_TEST_CASES)
    def test_make_pipelex_bundle_blueprint(self, test_name: str, mthds_content: str, expected_blueprint: PipelexBundleBlueprint):
        """Test making blueprint from various valid MTHDS content."""
        blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)

        pretty_print(blueprint, title=f"Blueprint {test_name}")
        pretty_print(expected_blueprint, title=f"Expected blueprint {test_name}")
        assert blueprint == expected_blueprint

    @pytest.mark.parametrize(("test_name", "invalid_mthds_content", "expected_exception"), InterpreterTestCases.ERROR_TEST_CASES)
    def test_invalid_mthds_should_raise_exception(self, test_name: str, invalid_mthds_content: str, expected_exception: type[Exception]):
        """Test that invalid MTHDS content raises appropriate exceptions."""
        log.verbose(f"Testing invalid MTHDS content: {test_name}")
        with pytest.raises(expected_exception):
            PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=invalid_mthds_content)
