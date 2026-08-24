"""Tests for the img-gen worker input-images capability guard.

`ImgGenWorkerAbstract._check_can_perform_job` rejects jobs carrying input images when
the model does not declare image inputs, before any provider call — so every worker
(Google Gemini native, chat-completions, args-factory based) fails early with an
explicit `ImgGenParameterError` instead of forwarding an unsupported request.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from typing_extensions import override

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.img_gen.img_gen_job import ImgGenJob

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_worker_abstract import ImgGenWorkerAbstract


class _StubImgGenWorker(ImgGenWorkerAbstract):
    """Minimal concrete worker recording whether the provider call was reached."""

    provider_called: bool = False

    @override
    async def _gen_image(self, img_gen_job: ImgGenJob) -> GeneratedImageRawDetails:
        self.provider_called = True
        return GeneratedImageRawDetails(actual_bytes=b"fake", size=None, mime_type="image/png")

    @override
    async def _gen_image_list(self, img_gen_job: ImgGenJob, *, nb_images: int) -> list[GeneratedImageRawDetails]:
        self.provider_called = True
        return []


def _make_worker(mocker: MockerFixture, *, is_img2img_supported: bool) -> _StubImgGenWorker:
    mock_model = mocker.MagicMock()
    mock_model.name = "nano-banana-test"
    mock_model.is_img2img_supported = is_img2img_supported
    return _StubImgGenWorker(inference_model=mock_model, reporting_delegate=None)


def _make_img_gen_job(mocker: MockerFixture, *, input_images: list[Any] | None) -> Any:
    job = mocker.MagicMock()
    job.img_gen_prompt.input_images = input_images
    return job


class TestImgGenWorkerInputImagesGuard:
    def test_input_images_on_text_only_model_raises(self, mocker: MockerFixture) -> None:
        """Input images on a model without image inputs raise a parameter error naming the model."""
        worker = _make_worker(mocker, is_img2img_supported=False)
        job = _make_img_gen_job(mocker, input_images=[mocker.MagicMock()])

        with pytest.raises(ImgGenParameterError, match="nano-banana-test"):
            worker._check_can_perform_job(img_gen_job=job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_input_images_on_img2img_model_passes(self, mocker: MockerFixture) -> None:
        """Input images on an img2img-capable model pass the guard."""
        worker = _make_worker(mocker, is_img2img_supported=True)
        job = _make_img_gen_job(mocker, input_images=[mocker.MagicMock()])

        worker._check_can_perform_job(img_gen_job=job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    def test_no_input_images_on_text_only_model_passes(self, mocker: MockerFixture) -> None:
        """A plain text-to-image job on a text-only model passes the guard."""
        worker = _make_worker(mocker, is_img2img_supported=False)
        job = _make_img_gen_job(mocker, input_images=None)

        worker._check_can_perform_job(img_gen_job=job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    @pytest.mark.asyncio
    async def test_gen_image_rejects_before_provider_call(self, mocker: MockerFixture) -> None:
        """The public gen_image flow raises before the provider implementation runs."""
        worker = _make_worker(mocker, is_img2img_supported=False)
        job = _make_img_gen_job(mocker, input_images=[mocker.MagicMock()])

        with pytest.raises(ImgGenParameterError, match="does not accept image inputs"):
            await worker.gen_image(img_gen_job=job)
        assert worker.provider_called is False

    @pytest.mark.asyncio
    async def test_gen_image_list_rejects_before_provider_call(self, mocker: MockerFixture) -> None:
        """The public gen_image_list flow raises before the provider implementation runs."""
        worker = _make_worker(mocker, is_img2img_supported=False)
        job = _make_img_gen_job(mocker, input_images=[mocker.MagicMock()])

        with pytest.raises(ImgGenParameterError, match="does not accept image inputs"):
            await worker.gen_image_list(img_gen_job=job, nb_images=2)
        assert worker.provider_called is False
