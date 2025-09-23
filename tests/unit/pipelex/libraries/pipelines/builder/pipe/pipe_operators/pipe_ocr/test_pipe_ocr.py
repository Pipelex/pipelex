"""
Test suite for PipeOcrBlueprint.to_core_blueprint conversion method.
"""

import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_ocr_builder import PipeOcrBlueprint
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint as PipeOcrBlueprintCore

from .test_data import PipeOcrTestCases


class TestPipeOcrBlueprintConversion:
    """Test PipeOcrBlueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,pipe_blueprint,pipe_code,domain,expected_core",
        PipeOcrTestCases.TEST_CASES,
    )
    def test_pipe_ocr_to_core(
        self,
        test_name: str,
        pipe_blueprint: PipeOcrBlueprint,
        pipe_code: str,
        domain: str,
        expected_core: PipeOcrBlueprintCore,
    ):
        """Test converting various pipe ocr blueprints to core blueprints."""
        result = pipe_blueprint.to_core_blueprint(pipe_code=pipe_code, domain=domain)
        assert result == expected_core
