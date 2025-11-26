import pytest
from pydantic import ValidationError

from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint


class TestPipeImgGenBlueprint:
    def test_validate_inputs_correct(self):
        blueprint = PipeImgGenBlueprint(
            inputs=None,
            img_gen_prompt="A beautiful sunset",
            output="Image",
        )
        assert blueprint.inputs is None
        assert blueprint.img_gen_prompt == "A beautiful sunset"

        blueprint = PipeImgGenBlueprint(
            inputs={"prompt": "ImgGenPrompt"},
            output="Image",
        )
        assert blueprint.nb_inputs == 1
        assert blueprint.input_names == ["prompt"]

    def test_validate_inputs_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            PipeImgGenBlueprint(
                inputs={},
                output="Image",
            )
        assert "If no inputs are provided, you must provide an 'img_gen_prompt' as attribute" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            PipeImgGenBlueprint(
                inputs={"prompt": "ImgGenPrompt"},
                img_gen_prompt="A beautiful sunset",
                output="Image",
            )
        assert "You must provide either an 'img_gen_prompt' as attribute or as a single text input, but not both" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            PipeImgGenBlueprint(
                inputs={"prompt1": "ImgGenPrompt", "prompt2": "ImgGenPrompt"},
                output="Image",
            )
        assert "Too many inputs provided for PipeImgGen" in str(exc_info.value)
