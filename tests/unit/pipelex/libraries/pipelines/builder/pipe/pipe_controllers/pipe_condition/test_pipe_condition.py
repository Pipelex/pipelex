"""
Test suite for PipeConditionBlueprint.to_core_blueprint conversion method.
"""

import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_condition import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import (
    PipeConditionBlueprint as PipeConditionBlueprintCore,
)

from .test_data import PipeConditionTestCases


class TestPipeConditionBlueprintConversion:
    """Test PipeConditionBlueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,pipe_blueprint,pipe_code,domain,expected_core",
        PipeConditionTestCases.TEST_CASES,
    )
    def test_pipe_condition_to_core(
        self,
        test_name: str,
        pipe_blueprint: PipeConditionBlueprint,
        pipe_code: str,
        domain: str,
        expected_core: PipeConditionBlueprintCore,
    ):
        """Test converting various pipe condition blueprints to core blueprints."""
        result = pipe_blueprint.to_core_blueprint(pipe_code=pipe_code, domain=domain)
        assert result == expected_core
