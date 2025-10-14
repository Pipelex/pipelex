import pytest

from pipelex.core.pipes.input_requirement_blueprint import InputRequirementBlueprint
from tests.unit.pipelex.builder.pipe.test_data_inputs import InputRequirementTestCases


class TestInputRequirementBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "input_spec", "expected_blueprint"),
        InputRequirementTestCases.TEST_CASES,
    )
    def test_input_requirement_spec_to_blueprint(
        self,
        test_name: str,  # noqa: ARG002
        input_spec: str,
        expected_blueprint: InputRequirementBlueprint,
    ):
        result = InputRequirementBlueprint(concept=input_spec)
        assert result == expected_blueprint
