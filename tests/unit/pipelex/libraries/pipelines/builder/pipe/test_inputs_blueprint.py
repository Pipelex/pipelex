import pytest

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint


from .test_data_inputs import InputRequirementTestCases


class TestInputRequirementBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,input_spec,domain,expected_blueprint",
        InputRequirementTestCases.TEST_CASES,
    )
    def test_input_requirement_spec_to_blueprint(
        self, test_name: str, input_spec: str, domain: str, expected_blueprint: InputRequirementBlueprint
    ):
        result = InputRequirementBlueprint(concept=input_spec)
        assert result == expected_blueprint
