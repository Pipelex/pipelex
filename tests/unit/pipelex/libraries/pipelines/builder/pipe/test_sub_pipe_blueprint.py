"""
Test suite for SubPipeBlueprint.to_core_sub_pipe conversion method.
"""

import pytest

from pipelex.libraries.pipelines.builder.pipe.sub_pipe import SubPipeBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint as SubPipeBlueprintCore

from .test_data_sub_pipe import SubPipeTestCases


class TestSubPipeBlueprintConversion:
    """Test SubPipeBlueprint.to_core_sub_pipe conversion."""

    @pytest.mark.parametrize(
        "test_name,sub_pipe_blueprint,expected_core",
        SubPipeTestCases.TEST_CASES,
    )
    def test_sub_pipe_to_core(self, test_name: str, sub_pipe_blueprint: SubPipeBlueprint, expected_core: SubPipeBlueprintCore):
        """Test converting various sub-pipe blueprints to core blueprints."""
        result = sub_pipe_blueprint.to_core_sub_pipe()
        assert result == expected_core
