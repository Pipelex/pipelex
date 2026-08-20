"""Capture-stage test for the OpenAI image-generation token-usage path.

Image-gen usage (``ImgGenTokensUsage.nb_tokens_by_category``) is read from the
``ImagesResponse.usage`` block inside ``_gen_image_list``. No test asserts this
capture today — non-LLM usage is uncovered in every mode. This pins it by
driving the worker with a canned ImagesResponse carrying a usage block.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import openai
import pytest

from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import (
    AspectRatio,
    Background,
    ImgGenJobConfig,
    ImgGenJobParams,
    ImgGenJobReport,
)
from pipelex.cogt.img_gen.img_gen_model_rules import ImgGenArgTopic, ImgGenModelRules
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.providers.openai.openai_img_gen_worker import OpenAIImgGenWorker
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.tools.misc.image_utils import ImageFormat

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _minimal_text_to_image_rules() -> ImgGenModelRules:
    """Rules without INPUT_IMAGES so the worker routes to ``images.generate`` (not ``images.edit``)."""
    return {ImgGenArgTopic.PROMPT: "positive_only", ImgGenArgTopic.NUM_IMAGES: "fal"}


def _make_img_gen_model() -> InferenceModelSpec:
    return InferenceModelSpec(
        backend_name="openai",
        name="gpt-image-2",
        sdk="openai_img_gen",
        model_type=ModelType.IMG_GEN,
        model_id="gpt-image-2",
        inputs=["text"],
        outputs=["image"],
        costs={CostCategory.INPUT: 8, CostCategory.OUTPUT: 30},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
        rules=_minimal_text_to_image_rules(),
    )


def _make_img_gen_job() -> ImgGenJob:
    return ImgGenJob(
        img_gen_prompt=ImgGenPrompt(positive_text="A test prompt"),
        job_params=ImgGenJobParams(
            aspect_ratio=AspectRatio.SQUARE,
            size=None,
            background=Background.OPAQUE,
            input_fidelity=None,
            output_format=ImageFormat.PNG,
        ),
        job_config=ImgGenJobConfig(is_sync_mode=False),
        job_report=ImgGenJobReport(),
        job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", user_id="test-user", pipeline_run_id="test-run")),
    )


class TestOpenAIImgGenWorkerUsageCapture:
    """``_gen_image_list`` reads ``ImagesResponse.usage`` into the job's tokens_usage."""

    @pytest.mark.asyncio
    async def test_worker_captures_img_gen_usage(self, mocker: MockerFixture) -> None:
        openai_client = openai.AsyncOpenAI(api_key="sk-test")

        class FakeImageData:
            b64_json = "dGVzdA=="

        class FakeUsage:
            input_tokens = 11
            output_tokens = 22

        class FakeImagesResponse:
            def __init__(self) -> None:
                self.data = [FakeImageData()]
                self.output_format = "png"
                self.size = "1024x1024"
                self.usage = FakeUsage()

        mocker.patch.object(openai_client.images, "generate", mocker.AsyncMock(return_value=FakeImagesResponse()))

        worker = OpenAIImgGenWorker(sdk_instance=openai_client, inference_model=_make_img_gen_model())
        job = _make_img_gen_job()

        await worker.gen_image_list(img_gen_job=job, nb_images=1)

        captured = job.job_report.img_gen_tokens_usage
        assert captured is not None
        assert captured.nb_tokens_by_category == {TokenCategory.INPUT: 11, TokenCategory.OUTPUT: 22}
