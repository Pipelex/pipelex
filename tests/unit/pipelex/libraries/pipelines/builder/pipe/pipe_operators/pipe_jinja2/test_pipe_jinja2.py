"""
Test suite for PipeJinja2Blueprint.to_core_blueprint conversion method.
"""

import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_jinja2_builder import PipeJinja2Blueprint
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import (
    PipeJinja2Blueprint as PipeJinja2BlueprintCore,
)

from .test_data import PipeJinja2TestCases


class TestPipeJinja2BlueprintConversion:
    """Test PipeJinja2Blueprint.to_core_blueprint conversion."""

    @pytest.mark.parametrize(
        "test_name,pipe_blueprint,pipe_code,domain,expected_core",
        PipeJinja2TestCases.TEST_CASES,
    )
    def test_pipe_jinja2_to_core(
        self,
        test_name: str,
        pipe_blueprint: PipeJinja2Blueprint,
        pipe_code: str,
        domain: str,
        expected_core: PipeJinja2BlueprintCore,
    ):
        """Test converting various pipe jinja2 blueprints to core blueprints."""
        result = pipe_blueprint.to_core_blueprint(pipe_code=pipe_code, domain=domain)
        assert result == expected_core
