"""Image generation test fixtures."""

import pytest

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams
from pipelex.tools.misc.image_utils import ImageFormat

# ================================================================================================
# Image generation model collections are now defined in .pipelex-dev/test_profiles.toml
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
        # ImgGenJobParams(
        #     aspect_ratio=AspectRatio.PORTRAIT_9_16,
        #     background=Background.OPAQUE,
        #     quality=Quality.MEDIUM,
        #     guidance_scale=2.5,
        #     is_moderated=None,
        #     safety_tolerance=1,
        #     is_raw=None,
        #     output_format=ImageFormat.PNG,
        # ),
        # ImgGenJobParams(
        #     aspect_ratio=AspectRatio.LANDSCAPE_4_3,
        #     background=Background.OPAQUE,
        #     quality=Quality.HIGH,
        #     guidance_scale=2.5,
        #     is_moderated=None,
        #     safety_tolerance=1,
        #     is_raw=None,
        #     output_format=ImageFormat.JPEG,
        # ),
    ],
)
def img_gen_job_params(request: pytest.FixtureRequest) -> ImgGenJobParams:
    assert isinstance(request.param, ImgGenJobParams)
    return request.param
