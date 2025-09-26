import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_jinja2_spec import PipeJinja2Spec
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint

from .test_data import PipeJinja2TestCases


class TestPipeJinja2BlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,pipe_spec,expected_blueprint",
        PipeJinja2TestCases.TEST_CASES,
    )
    def test_pipe_jinja2_spec_to_blueprint(
        self,
        test_name: str,
        pipe_spec: PipeJinja2Spec,
        expected_blueprint: PipeJinja2Blueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
