import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint

from .test_data import PipeConditionTestCases


class TestPipeConditionBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,pipe_spec,domain,expected_blueprint",
        PipeConditionTestCases.TEST_CASES,
    )
    def test_pipe_condition_spec_to_blueprint(
        self,
        test_name: str,
        pipe_spec: PipeConditionSpec,
        domain: str,
        expected_blueprint: PipeConditionBlueprint,
    ):
        result = pipe_spec.to_blueprint(pipe_code=pipe_spec.the_pipe_code, domain=domain)
        assert result == expected_blueprint
