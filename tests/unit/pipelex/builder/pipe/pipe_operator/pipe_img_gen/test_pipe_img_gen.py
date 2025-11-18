import pytest

from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from tests.unit.pipelex.builder.pipe.pipe_operator.pipe_img_gen.test_data import PipeImgGenTestCases


class TestPipeImgGenBlueprintConversion:
    @pytest.mark.parametrize(
        ("test_name", "pipe_spec", "expected_blueprint"),
        PipeImgGenTestCases.TEST_CASES,
    )
    def test_pipe_img_gen_spec_to_blueprint(
        self,
        test_name: str,  # noqa: ARG002
        pipe_spec: PipeImgGenSpec,
        expected_blueprint: PipeImgGenBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        assert result == expected_blueprint
