import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint

from .test_data import PipeBatchTestCases


class TestPipeBatchBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,pipe_spec,expected_blueprint",
        PipeBatchTestCases.TEST_CASES,
    )
    def test_pipe_batch_spec_to_blueprint(
        self,
        test_name: str,
        pipe_spec: PipeBatchSpec,
        expected_blueprint: PipeBatchBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
