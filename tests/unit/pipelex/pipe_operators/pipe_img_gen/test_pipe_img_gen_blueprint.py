from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, SizeTier
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.validation_error_types import PipeValidationErrorType
from tests.unit.pipelex.pipe_operators.input_check_helpers import refused_input_error
from tests.unit.pipelex.pipe_operators.pipe_img_gen.data import PipeImgGenInputCheckTestCases


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
        error = refused_input_error(
            blueprint_class=PipeImgGenBlueprint,
            blueprint_kwargs={
                "description": "lorem ipsum",
                "inputs": {"topic": "Text"},
                "output": "Image",
                "prompt": "Sketch black and white illustration of: $bingo",
            },
        )
        assert error.error_type == PipeValidationErrorType.MISSING_INPUT_VARIABLE
        assert error.variable_names == ["bingo"]

    @pytest.mark.parametrize(
        ("test_id", "blueprint_kwargs", "expected_error_type", "expected_variable_names"),
        PipeImgGenInputCheckTestCases.REFUSED_CASES,
    )
    def test_input_check_refused(
        self,
        test_id: str,
        blueprint_kwargs: dict[str, Any],
        expected_error_type: PipeValidationErrorType,
        expected_variable_names: list[str],
    ):
        error = refused_input_error(blueprint_class=PipeImgGenBlueprint, blueprint_kwargs=blueprint_kwargs)
        assert error.error_type == expected_error_type, test_id
        assert error.variable_names == expected_variable_names, test_id

    @pytest.mark.parametrize(
        ("test_id", "blueprint_kwargs"),
        PipeImgGenInputCheckTestCases.ACCEPTED_CASES,
    )
    def test_input_check_accepted(self, test_id: str, blueprint_kwargs: dict[str, Any]):
        blueprint = PipeImgGenBlueprint.model_validate(blueprint_kwargs)
        assert set(blueprint.input_names) == set(blueprint_kwargs["inputs"]), test_id

    def test_size_tier_composes_with_aspect_ratio(self):
        """A size tier and an aspect_ratio are complementary and may be set together."""
        blueprint = PipeImgGenBlueprint.model_validate(
            {
                "description": "lorem ipsum",
                "inputs": None,
                "output": "Image",
                "prompt": "A beautiful sunset",
                "aspect_ratio": "landscape_16_9",
                "size": "2k",
            }
        )
        assert blueprint.size is SizeTier.TWO_K
        assert blueprint.aspect_ratio is AspectRatio.LANDSCAPE_16_9

    def test_size_tier_alone_ok(self):
        blueprint = PipeImgGenBlueprint.model_validate(
            {
                "description": "lorem ipsum",
                "inputs": None,
                "output": "Image",
                "prompt": "A beautiful sunset",
                "size": "4k",
            }
        )
        assert blueprint.size is SizeTier.FOUR_K
        assert blueprint.aspect_ratio is None

    def test_exact_size_alone_ok(self):
        blueprint = PipeImgGenBlueprint.model_validate(
            {
                "description": "lorem ipsum",
                "inputs": None,
                "output": "Image",
                "prompt": "A beautiful sunset",
                "size": "2048x1152",
            }
        )
        assert blueprint.size == ImageSize(width=2048, height=1152)
        assert blueprint.aspect_ratio is None

    def test_exact_size_with_aspect_ratio_rejected(self):
        """An exact size implies the aspect ratio, so setting both is a validation error."""
        with pytest.raises(ValidationError, match="aspect_ratio"):
            PipeImgGenBlueprint.model_validate(
                {
                    "description": "lorem ipsum",
                    "inputs": None,
                    "output": "Image",
                    "prompt": "A beautiful sunset",
                    "aspect_ratio": "landscape_16_9",
                    "size": "2048x1152",
                }
            )

    def test_aspect_ratio_alone_ok(self):
        blueprint = PipeImgGenBlueprint.model_validate(
            {
                "description": "lorem ipsum",
                "inputs": None,
                "output": "Image",
                "prompt": "A beautiful sunset",
                "aspect_ratio": "landscape_16_9",
            }
        )
        assert blueprint.aspect_ratio is AspectRatio.LANDSCAPE_16_9
        assert blueprint.size is None
