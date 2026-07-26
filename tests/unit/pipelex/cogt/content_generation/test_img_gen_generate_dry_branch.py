"""Unit tests for the ``run_mode == DRY`` branch in the img-gen leaf (img_gen_generate).

The DRY branch sits at the ``*_and_store`` layer, ABOVE the raw provider leaf (eng review D10):
a dry run must perform no provider call and no storage IO. Contract: under DRY the worker and the
``GeneratedContentFactory`` are never touched, and the returned ``ImageContent`` are URL-only mocks
carrying the prompt stamps; LIVE keeps the real generate-and-store path.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import ImgGenAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.img_gen_generate import img_gen_image_list_and_store, img_gen_single_image_and_store
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.system.job_metadata import JobMetadata


class TestImgGenGenerateDryBranch:
    def _assignment(self, *, run_mode: PipeRunMode, nb_images: int = 1) -> ImgGenAssignment:
        return ImgGenAssignment(
            job_metadata=JobMetadata(user_id="u", pipeline_run_id="run_img_dry"),
            cogt_run_params=CogtRunParams(run_mode=run_mode),
            img_gen_handle="mock-img-handle",
            img_gen_prompt=ImgGenPrompt(positive_text="a red apple", negative_text="no worms"),
            img_gen_job_params=ImgGenJobParams(aspect_ratio=AspectRatio.SQUARE, background=Background.AUTO),
            img_gen_job_config=ImgGenJobConfig(is_sync_mode=True),
            nb_images=nb_images,
        )

    @pytest.mark.asyncio
    async def test_dry_single_skips_provider_and_storage(self, mocker: MockerFixture) -> None:
        """DRY single image: no worker call, no storage IO, URL-only mock with prompt stamps."""
        worker_spy = mocker.patch("pipelex.cogt.content_generation.img_gen_generate.get_img_gen_worker")
        factory = mocker.MagicMock()

        image_content = await img_gen_single_image_and_store(
            img_gen_assignment=self._assignment(run_mode=PipeRunMode.DRY),
            generated_content_factory=factory,
        )

        worker_spy.assert_not_called()
        factory.make_image_content.assert_not_called()
        assert image_content.url
        assert image_content.source_prompt == "a red apple"
        assert image_content.source_negative_prompt == "no worms"

    @pytest.mark.asyncio
    async def test_dry_single_yields_one_mock_even_with_nb_images_above_one(self, mocker: MockerFixture) -> None:
        """The single path mints exactly ONE mock regardless of the assignment's nb_images —
        matching the live single path's one-provider-call semantics — without mutating the
        assignment.
        """
        mocker.patch("pipelex.cogt.content_generation.img_gen_generate.get_img_gen_worker")
        assignment = self._assignment(run_mode=PipeRunMode.DRY, nb_images=3)

        image_content = await img_gen_single_image_and_store(
            img_gen_assignment=assignment,
            generated_content_factory=mocker.MagicMock(),
        )

        assert image_content.url
        assert assignment.nb_images == 3  # the normalization copies, never mutates

    @pytest.mark.asyncio
    async def test_dry_list_returns_nb_images_mocks_without_io(self, mocker: MockerFixture) -> None:
        """DRY image list: exactly nb_images URL-only mocks, no provider, no storage."""
        worker_spy = mocker.patch("pipelex.cogt.content_generation.img_gen_generate.get_img_gen_worker")
        factory = mocker.MagicMock()

        image_contents = await img_gen_image_list_and_store(
            img_gen_assignment=self._assignment(run_mode=PipeRunMode.DRY, nb_images=3),
            generated_content_factory=factory,
        )

        worker_spy.assert_not_called()
        factory.make_image_content.assert_not_called()
        assert len(image_contents) == 3
        assert all(image_content.url for image_content in image_contents)

    @pytest.mark.asyncio
    async def test_live_single_runs_provider_and_stores(self, mocker: MockerFixture) -> None:
        """LIVE keeps the real path: provider generates, factory stores."""
        worker = mocker.MagicMock()
        worker.gen_image = mocker.AsyncMock(return_value=mocker.MagicMock())
        mocker.patch("pipelex.cogt.content_generation.img_gen_generate.get_img_gen_worker", return_value=worker)
        mocker.patch(
            "pipelex.cogt.content_generation.img_gen_generate.ImgGenJobFactory.make_img_gen_job_from_prompt", return_value=mocker.MagicMock()
        )
        factory = mocker.MagicMock()
        factory.make_image_content = mocker.AsyncMock(return_value=mocker.MagicMock())

        await img_gen_single_image_and_store(
            img_gen_assignment=self._assignment(run_mode=PipeRunMode.LIVE),
            generated_content_factory=factory,
        )

        worker.gen_image.assert_awaited_once()
        factory.make_image_content.assert_awaited_once()
