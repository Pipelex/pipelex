from typing import Callable

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.img_gen.pipe_img_gen import PipeImgGen
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.runtime_hub import get_model_deck


def _llm_only_handle() -> str:
    """A bare handle the booted deck serves as an LLM and never as an image-generation model."""
    model_deck = get_model_deck()
    for handle in model_deck.inference_models.handles_of_type(model_type=ModelType.LLM):
        if model_deck.is_served_only_as_other_types(name=handle, model_type=ModelType.IMG_GEN):
            return handle
    pytest.fail("The test deck serves no LLM that is not also an image-generation model")


def _refusal_of(*, model: str) -> PipeOperatorModelChoiceError:
    blueprint = PipeImgGenBlueprint(description="Paint the scene", inputs={}, output="Image", prompt="A lighthouse at dusk", model=model)
    with pytest.raises(PipeOperatorModelChoiceError) as exc_info:
        PipeFactory[PipeImgGen].make_from_blueprint(domain_code="model_choice_code", pipe_code="paint_scene", blueprint=blueprint)
    return exc_info.value


class TestPipeImgGenModelChoiceCode:
    def test_an_llm_named_in_an_image_step_reads_capability_unsupported(self, load_empty_library: Callable[[], str]) -> None:
        """The located refusal keeps its cause's code: the model exists and is served, only not as an image model."""
        load_empty_library()

        refusal = _refusal_of(model=_llm_only_handle())

        assert refusal.field_name == "model"
        assert refusal.to_error_report().code == CoreCode.MODEL_CAPABILITY_UNSUPPORTED

    def test_a_model_no_deck_defines_reads_unknown(self, load_empty_library: Callable[[], str]) -> None:
        load_empty_library()

        refusal = _refusal_of(model="no-such-painter-anywhere")

        assert refusal.to_error_report().code == CoreCode.MODEL_UNKNOWN
