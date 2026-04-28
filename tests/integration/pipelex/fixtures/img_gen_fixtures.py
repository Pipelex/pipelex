"""Image generation test fixtures."""

import pytest

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams, Quality
from pipelex.cogt.img_gen.img_gen_param_support import ImgGenParamSupport
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec


def skip_if_img_gen_params_unsupported(
    inference_model: InferenceModelSpec,
    params: ImgGenJobParams,
    *,
    has_input_images: bool = False,
) -> None:
    """Call from tests: pytest.skip if any param value isn't supported by the model's rules."""
    if inference_model.rules is None:
        return
    reasons = ImgGenParamSupport.check_job_params(
        rules=inference_model.rules,
        params=params,
        model_name=inference_model.name,
        has_input_images=has_input_images,
    )
    if reasons:
        pytest.skip(f"Model '{inference_model.name}' does not support: {'; '.join(reasons)}")


# ================================================================================================
# Image generation model collections are now defined in .pipelex-dev/test_profiles.toml
# See [collections.img_gen] section for the full list organized by backend
# ================================================================================================


@pytest.fixture(
    params=[
        # ImgGenJobParams(
        #     aspect_ratio=AspectRatio.SQUARE,
        #     background=Background.OPAQUE,
        #     nb_steps=8,
        #     guidance_scale=2.5,
        #     is_moderated=None,
        #     safety_tolerance=1,
        #     is_raw=None,
        #     output_format=ImageFormat.PNG,
        # ),
        ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            background=Background.OPAQUE,
            quality=Quality.LOW,
            guidance_scale=None,
            is_moderated=None,
            safety_tolerance=None,
            is_raw=None,
            output_format=None,
        ),
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
