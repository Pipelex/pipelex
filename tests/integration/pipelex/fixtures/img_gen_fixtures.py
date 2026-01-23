"""Image generation test fixtures."""

import pytest

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams, Quality
from pipelex.hub import get_model_deck
from pipelex.tools.misc.image_utils import ImageFormat


def is_img_gen_handle_supported(img_gen_handle: str) -> bool:
    """Check if an img_gen handle is available in the current model deck."""
    model_deck = get_model_deck()
    return model_deck.is_handle_defined(img_gen_handle)


# ================================================================================================
# Image generation model collections are now defined in .pipelex/test_profiles.toml
# See [collections.img_gen] section for the full list organized by backend
# ================================================================================================


@pytest.fixture(
    params=[
        ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            background=Background.OPAQUE,
            nb_steps=8,
            guidance_scale=2.5,
            is_moderated=None,
            safety_tolerance=1,
            is_raw=None,
            output_format=ImageFormat.PNG,
        ),
        ImgGenJobParams(
            aspect_ratio=AspectRatio.PORTRAIT_9_16,
            background=Background.OPAQUE,
            quality=Quality.MEDIUM,
            guidance_scale=2.5,
            is_moderated=None,
            safety_tolerance=1,
            is_raw=None,
            output_format=ImageFormat.JPEG,
        ),
        ImgGenJobParams(
            aspect_ratio=AspectRatio.LANDSCAPE_4_3,
            background=Background.OPAQUE,
            quality=Quality.HIGH,
            guidance_scale=2.5,
            is_moderated=None,
            safety_tolerance=1,
            is_raw=None,
            output_format=ImageFormat.PNG,
        ),
    ],
)
def img_gen_job_params(request: pytest.FixtureRequest) -> ImgGenJobParams:
    assert isinstance(request.param, ImgGenJobParams)
    return request.param
