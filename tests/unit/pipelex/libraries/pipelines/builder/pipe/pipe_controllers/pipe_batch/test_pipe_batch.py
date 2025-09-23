"""
Test suite for PipeBatchBlueprint.to_core_blueprint conversion method.
"""

import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint

from .test_data import PipeBatchTestCases


class TestPipeBatchBlueprintConversion:
    """Test PipeBatchBlueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,pipe_blueprint,pipe_code,domain,expected_core",
        PipeBatchTestCases.TEST_CASES,
    )
    def test_pipe_batch_to_core(
        self,
        test_name: str,
        pipe_blueprint: PipeBatchSpec,
        pipe_code: str,
        domain: str,
        expected_core: PipeBatchBlueprint,
    ):
        """Test converting various pipe batch blueprints to core blueprints."""
        result = pipe_blueprint.to_core_blueprint(pipe_code=pipe_code, domain=domain)
        assert result == expected_core
