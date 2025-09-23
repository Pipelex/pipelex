"""
Test suite for PipeParallelBlueprint.to_core_blueprint conversion method.
"""

import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint

from .test_data import PipeParallelTestCases


class TestPipeParallelBlueprintConversion:
    """Test PipeParallelBlueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,pipe_blueprint,pipe_code,domain,expected_core",
        PipeParallelTestCases.TEST_CASES,
    )
    def test_pipe_parallel_to_core(
        self,
        test_name: str,
        pipe_blueprint: PipeParallelSpec,
        pipe_code: str,
        domain: str,
        expected_core: PipeParallelBlueprint,
    ):
        """Test converting various pipe parallel blueprints to core blueprints."""
        result = pipe_blueprint.to_core_blueprint(pipe_code=pipe_code, domain=domain)
        assert result == expected_core
