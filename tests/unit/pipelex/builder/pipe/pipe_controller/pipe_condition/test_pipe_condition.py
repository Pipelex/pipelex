import pytest

from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from tests.unit.pipelex.builder.pipe.pipe_controller.pipe_condition.test_data import PipeConditionTestCases


class TestPipeConditionBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "pipe_spec", "expected_blueprint"),
        PipeConditionTestCases.TEST_CASES,
    )
    def test_pipe_condition_spec_to_blueprint(
        self,
        test_name: str,  # noqa: ARG002
        pipe_spec: PipeConditionSpec,
        expected_blueprint: PipeConditionBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
