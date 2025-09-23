"""
Test suite for base PipeBlueprint.to_core_blueprint conversion method.
"""

import pytest

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSpec

from .test_data_pipe import PipeBlueprintTestCases


class TestPipeBlueprintConversion:
    """Test base PipeBlueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,pipe_blueprint,pipe_code,domain,expected_core",
        PipeBlueprintTestCases.TEST_CASES,
    )
    def test_pipe_blueprint_to_core(
        self,
        test_name: str,
        pipe_blueprint: PipeSpec,
        pipe_code: str,
        domain: str,
        expected_core: PipeBlueprint,
    ):
        """Test converting various pipe blueprints to core blueprints."""
        result = pipe_blueprint.to_core_blueprint(pipe_code=pipe_code, domain=domain)
        assert result == expected_core
