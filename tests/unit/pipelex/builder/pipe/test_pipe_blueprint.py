import pytest

from pipelex.builder.pipe.pipe_signature import PipeSpec
from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from tests.unit.pipelex.builder.pipe.test_data_pipe import PipeBlueprintTestCases


class TestPipeBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "pipe_spec", "expected_blueprint"),
        PipeBlueprintTestCases.TEST_CASES,
    )
    def test_pipe_blueprint_to_core(
        self,
        test_name: str,  # noqa: ARG002
        pipe_spec: PipeSpec,
        expected_blueprint: PipeBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
