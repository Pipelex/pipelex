import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint

from tests.unit.pipelex.libraries.pipelines.builder.pipe.pipe_operators.pipe_func.test_data import PipeFuncTestCases


class TestPipeFuncBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,pipe_spec,expected_blueprint",
        PipeFuncTestCases.TEST_CASES,
    )
    def test_pipe_func_spec_to_blueprint(
        self,
        test_name: str,
        pipe_spec: PipeFuncSpec,
        expected_blueprint: PipeFuncBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
