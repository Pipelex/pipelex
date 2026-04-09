"""Config coverage test fixtures.

Override the parameterized job_params fixtures with single-value versions
to keep the test matrix minimal: one run per model, not per model x params.
"""

import pytest

from pipelex.cogt.extract.extract_job_components import ExtractJobParams
from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams
from pipelex.cogt.llm.llm_job_components import LLMJobParams
from pipelex.tools.misc.image_utils import ImageFormat


@pytest.fixture
def llm_job_params() -> LLMJobParams:
    return LLMJobParams(
        temperature=0.5,
        max_tokens=None,
        image_detail=PromptImageDetail.AUTO,
        seed=None,
    )


@pytest.fixture
def extract_job_params() -> ExtractJobParams:
    return ExtractJobParams(
        max_nb_images=None,
        should_caption_images=False,
        should_include_page_views=False,
        page_views_dpi=None,
        image_min_size=None,
    )


@pytest.fixture
def img_gen_job_params() -> ImgGenJobParams:
    return ImgGenJobParams(
        aspect_ratio=AspectRatio.SQUARE,
        background=Background.OPAQUE,
        nb_steps=8,
        guidance_scale=2.5,
        is_moderated=None,
        safety_tolerance=1,
        is_raw=None,
        output_format=ImageFormat.PNG,
    )
