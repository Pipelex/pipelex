"""
Test suite for PipeSequenceBlueprint.to_core_blueprint conversion method.
"""

import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_sequence_builder import PipeSequenceBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import (
    PipeSequenceBlueprint as PipeSequenceBlueprintCore,
)

from .test_data import PipeSequenceTestCases


class TestPipeSequenceBlueprintConversion:
    """Test PipeSequenceBlueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,pipe_blueprint,pipe_code,domain,expected_core",
        PipeSequenceTestCases.TEST_CASES,
    )
    def test_pipe_sequence_to_core(
        self,
        test_name: str,
        pipe_blueprint: PipeSequenceBlueprint,
        pipe_code: str,
        domain: str,
        expected_core: PipeSequenceBlueprintCore,
    ):
        """Test converting various pipe sequence blueprints to core blueprints."""
        result = pipe_blueprint.to_core_blueprint(pipe_code=pipe_code, domain=domain)
        assert result == expected_core
