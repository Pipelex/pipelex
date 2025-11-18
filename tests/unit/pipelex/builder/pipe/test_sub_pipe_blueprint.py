import pytest

from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from tests.unit.pipelex.builder.pipe.test_data_sub_pipe import SubPipeTestCases


class TestSubPipeBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "sub_pipe_spec", "expected_blueprint"),
        SubPipeTestCases.TEST_CASES,
    )
    def test_sub_pipe_to_core(self, test_name: str, sub_pipe_spec: SubPipeSpec, expected_blueprint: SubPipeBlueprint):  # noqa: ARG002
        result = sub_pipe_spec.to_blueprint()
        assert result == expected_blueprint
