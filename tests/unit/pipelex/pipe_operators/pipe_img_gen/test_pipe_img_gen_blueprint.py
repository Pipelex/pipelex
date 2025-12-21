import pytest
from pydantic import ValidationError

from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint


class TestPipeImgGenBlueprint:
    def test_validate_inputs_correct(self):
        blueprint = PipeImgGenBlueprint(
            description="lorem ipsum",
            inputs=None,
            output="Image",
            prompt="A beautiful sunset",
        )
        assert blueprint.inputs is None
        assert blueprint.prompt == "A beautiful sunset"

        blueprint = PipeImgGenBlueprint(
            description="lorem ipsum",
            inputs={"topic": "Text"},
            output="Image",
            prompt="Sketch black and white illustration of: $topic",
        )
        assert blueprint.nb_inputs == 1
        assert blueprint.input_names == ["topic"]

    def test_validate_inputs_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            PipeImgGenBlueprint(
                description="lorem ipsum",
                inputs={"topic": "Text"},
                output="Image",
                prompt="Sketch black and white illustration of: $bingo",
            )
        assert "Missing input variable(s) in prompt template: bingo" in str(exc_info.value)
