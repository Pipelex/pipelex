import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint

from .test_data import PipeParallelTestCases


class TestPipeParallelBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,pipe_spec,expected_blueprint",
        PipeParallelTestCases.TEST_CASES,
    )
    def test_pipe_parallel_spec_to_blueprint(
        self,
        test_name: str,
        pipe_spec: PipeParallelSpec,
        expected_blueprint: PipeParallelBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
