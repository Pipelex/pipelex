import pytest

from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.libraries.pipelines.builder.pipe.inputs_spec import InputRequirementSpec

from .test_data_inputs import InputRequirementTestCases


class TestInputRequirementBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,input_spec,domain,expected_blueprint",
        InputRequirementTestCases.TEST_CASES,
    )
    def test_input_requirement_spec_to_blueprint(
        self, test_name: str, input_spec: InputRequirementSpec, domain: str, expected_blueprint: InputRequirementBlueprint,
    ):
        result = input_spec.to_blueprint()
        assert result == expected_blueprint
