import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint

from tests.unit.pipelex.libraries.pipelines.builder.pipe.pipe_operators.pipe_jinja2.test_data import PipeComposeTestCases


class TestPipeComposeBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,pipe_spec,expected_blueprint",
        PipeComposeTestCases.TEST_CASES,
    )
    def test_pipe_compose_spec_to_blueprint(
        self,
        test_name: str,
        pipe_spec: PipeComposeSpec,
        expected_blueprint: PipeComposeBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
