"""Unit tests for the ``is_mock_inference`` hard guard in the img-gen leaf (img_gen_generate).

``--mock-inference`` has no leaf-level mock for image generation, so reaching the img-gen leaf under
the flag would dispatch to the real provider and spend. The leaf must fail loud instead: raise
``MockInferenceUnsupportedError`` before ``get_img_gen_worker`` is ever called. With the flag off, the
real worker path runs unchanged — proving the guard is keyed strictly on ``job_metadata.is_mock_inference``.
"""

from collections.abc import Awaitable, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import ImgGenAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.exceptions import MockInferenceUnsupportedError
from pipelex.cogt.content_generation.img_gen_generate import img_gen_image_list, img_gen_single_image
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.pipeline.job_metadata import JobMetadata


class TestImgGenGenerateMockGuard:
    def _assignment(self, *, is_mock_inference: bool) -> ImgGenAssignment:
        return ImgGenAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_img_guard", is_mock_inference=is_mock_inference),
            cogt_run_params=CogtRunParams(),
            img_gen_handle="mock-img-handle",
            img_gen_prompt=ImgGenPrompt(positive_text="a red apple"),
            img_gen_job_params=ImgGenJobParams(aspect_ratio=AspectRatio.SQUARE, background=Background.AUTO),
            img_gen_job_config=ImgGenJobConfig(is_sync_mode=True),
            nb_images=1,
        )

    @pytest.mark.parametrize("leaf", [img_gen_single_image, img_gen_image_list])
    @pytest.mark.asyncio
    async def test_mock_flag_raises_and_skips_worker(self, mocker: MockerFixture, leaf: Callable[[ImgGenAssignment], Awaitable[object]]) -> None:
        """is_mock_inference=True -> the leaf raises before any provider call (get_img_gen_worker untouched)."""
        worker_spy = mocker.patch("pipelex.cogt.content_generation.img_gen_generate.get_img_gen_worker")

        with pytest.raises(MockInferenceUnsupportedError):
            await leaf(self._assignment(is_mock_inference=True))

        worker_spy.assert_not_called()  # no provider call -> no spend

    @pytest.mark.asyncio
    async def test_no_flag_uses_real_worker(self, mocker: MockerFixture) -> None:
        """is_mock_inference=False -> the real worker path runs (get_img_gen_worker is called)."""
        sentinel = mocker.MagicMock()
        worker = mocker.MagicMock()
        worker.gen_image = mocker.AsyncMock(return_value=sentinel)
        worker_spy = mocker.patch("pipelex.cogt.content_generation.img_gen_generate.get_img_gen_worker", return_value=worker)
        mocker.patch(
            "pipelex.cogt.content_generation.img_gen_generate.ImgGenJobFactory.make_img_gen_job_from_prompt", return_value=mocker.MagicMock()
        )

        result = await img_gen_single_image(self._assignment(is_mock_inference=False))

        worker_spy.assert_called_once()
        assert result is sentinel
