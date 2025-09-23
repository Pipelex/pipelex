"""
Test suite for PipeFuncBlueprint.to_core_blueprint conversion method.
"""

import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_func_builder import PipeFuncBlueprint
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint as PipeFuncBlueprintCore

from .test_data import PipeFuncTestCases


class TestPipeFuncBlueprintConversion:
    """Test PipeFuncBlueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,pipe_blueprint,pipe_code,domain,expected_core",
        PipeFuncTestCases.TEST_CASES,
    )
    def test_pipe_func_to_core(
        self,
        test_name: str,
        pipe_blueprint: PipeFuncBlueprint,
        pipe_code: str,
        domain: str,
        expected_core: PipeFuncBlueprintCore,
    ):
        """Test converting various pipe func blueprints to core blueprints."""
        result = pipe_blueprint.to_core_blueprint(pipe_code=pipe_code, domain=domain)
        assert result == expected_core
