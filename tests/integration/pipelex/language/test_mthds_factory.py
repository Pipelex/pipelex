import pytest

from pipelex import pretty_print
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.language.mthds_factory import MthdsFactory
from tests.unit.pipelex.core.test_data import InterpreterTestCases


class TestMthdsFactoryIntegration:
    @pytest.mark.parametrize(("test_name", "expected_mthds_content", "blueprint"), InterpreterTestCases.VALID_TEST_CASES)
    def test_make_mthds_content(self, test_name: str, expected_mthds_content: str, blueprint: PipelexBundleBlueprint):
        mthds_content = MthdsFactory.make_mthds_content(blueprint=blueprint)
        pretty_print(mthds_content, title=f"MTHDS content {test_name}")
        pretty_print(expected_mthds_content, title=f"Expected MTHDS content {test_name}")
        assert mthds_content == expected_mthds_content
