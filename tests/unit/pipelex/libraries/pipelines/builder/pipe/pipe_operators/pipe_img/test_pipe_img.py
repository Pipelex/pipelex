"""
Test suite for PipeImgGenBlueprint.to_core_blueprint conversion method.
"""

import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_img_spec import PipeImgGenSpec
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint

from .test_data import PipeImgGenTestCases


class TestPipeImgGenBlueprintConversion:
    """Test PipeImgGenBlueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,pipe_blueprint,pipe_code,domain,expected_core",
        PipeImgGenTestCases.TEST_CASES,
    )
    def test_pipe_img_gen_to_core(
        self,
        test_name: str,
        pipe_blueprint: PipeImgGenSpec,
        pipe_code: str,
        domain: str,
        expected_core: PipeImgGenBlueprint,
    ):
        """Test converting various pipe img gen blueprints to core blueprints."""
        result = pipe_blueprint.to_core_blueprint(pipe_code=pipe_code, domain=domain)
        assert result == expected_core
