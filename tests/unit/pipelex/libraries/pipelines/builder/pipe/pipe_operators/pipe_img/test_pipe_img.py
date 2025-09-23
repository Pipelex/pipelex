import pytest

from pipelex.libraries.pipelines.builder.pipe.pipe_img_spec import PipeImgGenSpec
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint

from .test_data import PipeImgGenTestCases


class TestPipeImgGenBlueprintConversion:
    @pytest.mark.parametrize(
        "test_name,pipe_spec,expected_blueprint",
        PipeImgGenTestCases.TEST_CASES,
    )
    def test_pipe_img_gen_spec_to_blueprint(
        self,
        test_name: str,
        pipe_spec: PipeImgGenSpec,
        expected_blueprint: PipeImgGenBlueprint,
    ):
        result = pipe_spec.to_blueprint()
        from pipelex import pretty_print

        pretty_print(result, title=f"Result {test_name}")
        pretty_print(expected_blueprint, title=f"Expected {test_name}")
        assert result == expected_blueprint
