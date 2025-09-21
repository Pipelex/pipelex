"""
Test suite for InputRequirementBlueprint.to_core_input_requirement conversion method.
"""

import pytest

from pipelex.core.pipes.pipe_input_spec_blueprint import (
    InputRequirementBlueprint as InputRequirementBlueprintCore,
)
from pipelex.libraries.pipelines.builder.pipe.inputs import InputRequirementBlueprint

from .test_data_inputs import InputRequirementTestCases


class TestInputRequirementBlueprintConversion:
    """Test InputRequirementBlueprint.to_core_input_requirement conversion."""

    @pytest.mark.parametrize(
        "test_name,input_blueprint,domain,expected_core",
        InputRequirementTestCases.TEST_CASES,
    )
    def test_input_requirement_to_core(
        self, test_name: str, input_blueprint: InputRequirementBlueprint, domain: str, expected_core: InputRequirementBlueprintCore
    ):
        """Test converting various input requirement blueprints to core blueprints."""
        result = input_blueprint.to_core_input_requirement(domain=domain)
        assert result == expected_core
