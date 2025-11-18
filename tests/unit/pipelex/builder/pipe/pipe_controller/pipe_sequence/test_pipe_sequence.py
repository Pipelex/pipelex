import pytest

from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from tests.unit.pipelex.builder.pipe.pipe_controller.pipe_sequence.test_data import PipeSequenceTestCases


class TestPipeSequenceBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "pipe_spec", "expected_blueprint"),
        PipeSequenceTestCases.TEST_CASES,
    )
    def test_pipe_sequence_spec_to_blueprint(
        self,
        test_name: str,  # noqa: ARG002
        pipe_spec: PipeSequenceSpec,
        expected_blueprint: PipeSequenceBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
