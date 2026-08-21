"""Tests for the Google ImgGen worker wire payload: `image_config` carries the portable size.

Asserts the tier -> `image_size` token threading, the omission of `image_size` when the
job has no size set (provider default, never a silent upgrade), the exact-size grid
derivation, and the tier-aware dimensions stamped on the generated-image metadata.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest
from google.genai import types as genai_types

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, SizeTier
from pipelex.cogt.img_gen.img_gen_model_rules import AspectRatioTaxonomy, ImgGenArgTopic
from pipelex.providers.google.google_img_gen_worker import GoogleImgGenWorker


def _make_response(mocker: MockerFixture) -> Any:
    response = mocker.MagicMock()
    part = mocker.MagicMock()
    part.inline_data.data = b"fake-png-bytes"
    part.inline_data.mime_type = "image/png"
    candidate = mocker.MagicMock()
    candidate.content.parts = [part]
    response.candidates = [candidate]
    response.usage_metadata = None
    return response


def _make_worker(mocker: MockerFixture) -> GoogleImgGenWorker:
    worker = object.__new__(GoogleImgGenWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gemini-3-flash-image"
    mock_model.name = "nano-banana-2"
    mock_model.rules = {ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GEMINI_3_FLASH}
    worker.inference_model = mock_model

    mock_async_client = mocker.MagicMock()
    mock_async_client.models.generate_content = mocker.AsyncMock(return_value=_make_response(mocker))
    worker.genai_async_client = mock_async_client
    return worker


def _make_img_gen_job(mocker: MockerFixture, *, aspect_ratio: AspectRatio, size: SizeTier | ImageSize | None) -> Any:
    job = mocker.MagicMock()
    job.job_params.aspect_ratio = aspect_ratio
    job.job_params.size = size
    job.job_params.output_format = None
    job.img_gen_prompt.positive_text = "a cute cat"
    job.img_gen_prompt.input_images = None
    job.job_report.img_gen_tokens_usage = None
    return job


def _sent_image_config(worker: GoogleImgGenWorker) -> genai_types.ImageConfig:
    call_kwargs = cast("dict[str, Any]", worker.genai_async_client.models.generate_content.call_args.kwargs)  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
    config = call_kwargs["config"]
    assert isinstance(config, genai_types.GenerateContentConfig)
    assert config.image_config is not None
    return config.image_config


@pytest.mark.asyncio(loop_scope="class")
class TestGoogleImgGenWorkerPayload:
    async def test_tier_is_sent_as_image_size_token(self, mocker: MockerFixture) -> None:
        """A portable tier reaches the wire as Google's `image_size` token, with tier-aware metadata dims."""
        worker = _make_worker(mocker)
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.SQUARE, size=SizeTier.TWO_K)

        details = await worker._gen_image(img_gen_job=job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        image_config = _sent_image_config(worker)
        assert image_config.aspect_ratio == "1:1"
        assert image_config.image_size == "2K"
        assert details.size == ImageSize(width=2048, height=2048)

    async def test_unset_size_omits_image_size_param(self, mocker: MockerFixture) -> None:
        """No size on the job -> `image_size` stays unset on the wire (provider default), metadata stamps the 1K grid."""
        worker = _make_worker(mocker)
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.LANDSCAPE_16_9, size=None)

        details = await worker._gen_image(img_gen_job=job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        image_config = _sent_image_config(worker)
        assert image_config.aspect_ratio == "16:9"
        assert image_config.image_size is None
        assert details.size == ImageSize(width=1376, height=768)

    async def test_exact_size_derives_ratio_and_image_size(self, mocker: MockerFixture) -> None:
        """An exact WxH matching a grid cell derives both the ratio literal and the `image_size` token."""
        worker = _make_worker(mocker)
        job = _make_img_gen_job(mocker, aspect_ratio=AspectRatio.SQUARE, size=ImageSize(width=2752, height=1536))

        details = await worker._gen_image(img_gen_job=job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        image_config = _sent_image_config(worker)
        assert image_config.aspect_ratio == "16:9"
        assert image_config.image_size == "2K"
        assert details.size == ImageSize(width=2752, height=1536)
