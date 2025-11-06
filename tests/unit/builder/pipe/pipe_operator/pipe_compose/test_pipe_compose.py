import pytest

from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from tests.unit.builder.pipe.pipe_operator.pipe_compose.test_data import PipeComposeTestCases


class TestPipeComposeBlueprintConversion:
    @pytest.mark.parametrize(
        ("_test_name", "pipe_spec", "expected_blueprint"),
        PipeComposeTestCases.TEST_CASES,
    )
    def test_pipe_compose_spec_to_blueprint(
        self,
        _test_name: str,
        pipe_spec: PipeComposeSpec,
        expected_blueprint: PipeComposeBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
