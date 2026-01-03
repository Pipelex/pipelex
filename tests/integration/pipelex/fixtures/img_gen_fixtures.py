"""Image generation test fixtures."""

import pytest

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams, Quality
from pipelex.hub import get_model_deck
from pipelex.tools.misc.image_utils import ImageFormat
from tests.integration.pipelex.fixtures.routing_fixtures import ALL_BACKENDS, check_backend_supports_model


def is_img_gen_handle_supported(img_gen_handle: str) -> bool:
    """Check if an img_gen handle is available in the current model deck."""
    model_deck = get_model_deck()
    return model_deck.is_handle_defined(img_gen_handle)


def is_img_gen_handle_supported_by_enabled_backends(img_gen_handle: str) -> bool:
    """Check if an img_gen handle is supported by at least one enabled backend."""
    return any(check_backend_supports_model(backend, img_gen_handle) for backend in ALL_BACKENDS)


# ================================================================================================
# Image Generation Handles by Backend
# Comment out handles you don't want to test
# ================================================================================================

# --- Stable Diffusion Models ---------------------------------------------------------------------------------
STABLE_DIFFUSION_IMG_GEN_MODELS = [
    "fast-lightning-sdxl",
]

# --- FAL Models ---------------------------------------------------------------------------------
FAL_IMG_GEN_MODELS = [
    # "flux-pro",
    # "flux-pro/v1.1",
    # "flux-pro/v1.1-ultra",
    "flux-2",
]

# --- OpenAI Models ------------------------------------------------------------------------------
OPENAI_IMG_GEN_MODELS = [
    "gpt-image-1",
    "gpt-image-1-mini",
    "gpt-image-1.5",
]

# --- Google Models --------------------------------------------------------------------------
GOOGLE_IMG_GEN_MODELS = [
    "nano-banana",
    "nano-banana-pro",
]

# --- Qwen Models --------------------------------------------------------------------------
QWEN_IMG_GEN_MODELS = [
    "qwen-image",
]

# --- All Image Generation Handles ---------------------------------------------------------------
ALL_IMG_GEN_HANDLES = [
    # *STABLE_DIFFUSION_IMG_GEN_MODELS,
    # *FAL_IMG_GEN_MODELS,
    *OPENAI_IMG_GEN_MODELS,
    *GOOGLE_IMG_GEN_MODELS,
    # *QWEN_IMG_GEN_MODELS,
]


@pytest.fixture(
    params=ALL_IMG_GEN_HANDLES,
)
def img_gen_handle(request: pytest.FixtureRequest) -> str:
    assert isinstance(request.param, str)
    img_gen_handle_param = request.param
    if not is_img_gen_handle_supported(img_gen_handle_param):
        pytest.skip(f"Image generation handle '{img_gen_handle_param}' not available in model deck")
    if not is_img_gen_handle_supported_by_enabled_backends(img_gen_handle_param):
        pytest.skip(f"Image generation handle '{img_gen_handle_param}' not supported by any enabled backend")
    return img_gen_handle_param


@pytest.fixture(
    params=[
        ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            background=Background.OPAQUE,
            nb_steps=10,
            guidance_scale=2.5,
            is_moderated=None,
            safety_tolerance=1,
            is_raw=None,
            output_format=ImageFormat.PNG,
        ),
        # ImgGenJobParams(
        #     aspect_ratio=AspectRatio.PORTRAIT_9_16,
        #     background=Background.OPAQUE,
        #     quality=Quality.MEDIUM,
        #     guidance_scale=2.5,
        #     is_moderated=None,
        #     safety_tolerance=1,
        #     is_raw=None,
        #     output_format=ImageFormat.JPEG,
        # ),
        # ImgGenJobParams(
        #     aspect_ratio=AspectRatio.LANDSCAPE_3_2,
        #     background=Background.OPAQUE,
        #     quality=Quality.HIGH,
        #     guidance_scale=2.5,
        #     is_moderated=None,
        #     safety_tolerance=1,
        #     is_raw=None,
        #     output_format=ImageFormat.PNG,
        # ),
    ],
)
def img_gen_job_params(request: pytest.FixtureRequest) -> ImgGenJobParams:
    assert isinstance(request.param, ImgGenJobParams)
    return request.param
