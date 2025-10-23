import pytest

from pipelex import log
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from tests.unit.builder.pipe.pipe_controller.pipe_parallel.test_data import PipeParallelTestCases


class TestPipeParallelBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "pipe_spec", "expected_blueprint"),
        PipeParallelTestCases.TEST_CASES,
    )
    def test_pipe_parallel_spec_to_blueprint(
        self,
        test_name: str,
        pipe_spec: PipeParallelSpec,
        expected_blueprint: PipeParallelBlueprint,
    ):
        log.verbose(f"Testing {test_name}")
        result = pipe_spec.to_blueprint()
        expected_blueprint.source = None
        assert result == expected_blueprint
