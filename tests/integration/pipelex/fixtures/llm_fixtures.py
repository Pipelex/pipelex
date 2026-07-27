"""LLM-related test fixtures."""

import pytest

from pipelex import log
from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.runtime_hub import get_model_deck

# ================================================================================================
# LLM model collections are now defined in .pipelex-dev/test_profiles.toml
# See [collections.llm] section for the full list organized by manufacturer
# ================================================================================================


@pytest.fixture(
    params=[
        LLMJobParams(
            temperature=0.5,
            max_tokens=None,
            image_detail=PromptImageDetail.AUTO,
            seed=None,
        ),
    ],
)
def llm_job_params(request: pytest.FixtureRequest) -> LLMJobParams:
    assert isinstance(request.param, LLMJobParams)
    return request.param


@pytest.fixture(
    params=[
        "$writing-creative",
    ],
)
def llm_preset_id(request: pytest.FixtureRequest) -> str:
    """Fixture for testing LLM presets (not model handles).

    This tests the preset functionality where an LLM setting is looked up
    by preset ID and used to configure the LLM worker.
    """
    assert isinstance(request.param, str)
    llm_preset_id_param = request.param
    if not _is_llm_preset_supported(llm_preset_id=llm_preset_id_param):
        pytest.skip(f"LLM preset '{llm_preset_id_param}' not supported")
    return llm_preset_id_param


def _is_llm_preset_supported(llm_preset_id: str) -> bool:
    """Check if an LLM preset is supported by at least one enabled backend."""
    llm_setting = get_model_deck().get_llm_setting(llm_choice=llm_preset_id)
    model_handle = llm_setting.model
    model_deck = get_model_deck()
    inference_model = model_deck.get_optional_inference_model(model_handle=model_handle, model_type=ModelType.LLM)
    if inference_model is None:
        return False
    log.debug(f"Inference model found!! {inference_model}")
    return True
