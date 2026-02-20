"""Tests for ImgGenArgsFactory input images validation.

Verifies that input images are properly validated when the model rules
don't include INPUT_IMAGES topic - preventing silent degradation to text-to-image.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageUri
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import (
    AspectRatio,
    Background,
    ImgGenJobConfig,
    ImgGenJobParams,
    ImgGenJobReport,
)
from pipelex.cogt.img_gen.img_gen_model_rules import (
    ImgGenArgTopic,
    ImgGenModelRules,
    InputImagesTaxonomy,
)
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.misc.filetype_utils import FileType
from pipelex.tools.uri.prepared_file import PreparedFileBase64

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestImgGenArgsFactory:
    """Tests for ImgGenArgsFactory.make_args_for_model validation of input images."""

    @staticmethod
    def _make_test_job(input_images: list[PromptImage] | None = None) -> ImgGenJob:
        """Create a test ImgGenJob with optional input images."""
        return ImgGenJob(
            img_gen_prompt=ImgGenPrompt(
                positive_text="A test prompt",
                input_images=input_images,
            ),
            job_params=ImgGenJobParams(
                aspect_ratio=AspectRatio.SQUARE,
                background=Background.OPAQUE,
            ),
            job_config=ImgGenJobConfig(is_sync_mode=False),
            job_report=ImgGenJobReport(),
            job_metadata=JobMetadata(user_id="test-user", pipeline_run_id="test-run"),
        )

    @staticmethod
    def _make_minimal_rules_without_input_images() -> ImgGenModelRules:
        """Create minimal model rules that do NOT include INPUT_IMAGES topic."""
        return {
            ImgGenArgTopic.PROMPT: "positive_only",
            ImgGenArgTopic.NUM_IMAGES: "fal",
        }

    @staticmethod
    def _make_rules_with_input_images() -> ImgGenModelRules:
        """Create model rules that include INPUT_IMAGES topic."""
        return {
            ImgGenArgTopic.PROMPT: "positive_only",
            ImgGenArgTopic.NUM_IMAGES: "fal",
            ImgGenArgTopic.INPUT_IMAGES: InputImagesTaxonomy.GPT_IMAGE,
        }

    @pytest.mark.asyncio
    async def test_input_images_provided_without_rules_raises_error(self) -> None:
        """When input_images are provided but INPUT_IMAGES is NOT in model rules, raise ImgGenParameterError.

        This prevents silent degradation from image-to-image to text-to-image.
        """
        input_images = cast("list[PromptImage]", [PromptImageUri(uri="https://example.com/image.png")])
        job = self._make_test_job(input_images=input_images)
        rules = self._make_minimal_rules_without_input_images()

        with pytest.raises(ImgGenParameterError) as exc_info:
            await ImgGenArgsFactory.make_args_for_model(
                model_rules=rules,
                img_gen_job=job,
                nb_images=1,
                model_id="test-model",
            )

        error_message = str(exc_info.value)
        assert "input images" in error_message.lower()
        assert "not" in error_message.lower()

    @pytest.mark.asyncio
    async def test_input_images_provided_with_rules_succeeds(self, mocker: MockerFixture) -> None:
        """When input_images are provided AND INPUT_IMAGES IS in model rules, no error is raised."""
        input_images = cast("list[PromptImage]", [PromptImageUri(uri="https://example.com/image.png")])
        job = self._make_test_job(input_images=input_images)
        rules = self._make_rules_with_input_images()

        # Mock prep_prompt_images to avoid network calls
        mock_prepped = [
            PreparedFileBase64(
                base64_data="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                file_type=FileType(extension="png", mime="image/png"),
            )
        ]
        mocker.patch(
            "pipelex.cogt.img_gen.img_gen_args_factory.prep_prompt_images",
            new_callable=mocker.AsyncMock,
            return_value=mock_prepped,
        )
        # Should not raise - validation passes
        result = await ImgGenArgsFactory.make_args_for_model(
            model_rules=rules,
            img_gen_job=job,
            nb_images=1,
            model_id="test-model",
        )

        assert isinstance(result, dict)
        assert "image" in result  # GPT_IMAGE taxonomy creates "image" key

    @pytest.mark.asyncio
    async def test_no_input_images_without_rules_succeeds(self) -> None:
        """When NO input_images are provided AND INPUT_IMAGES is NOT in model rules, no error.

        This is the standard text-to-image case.
        """
        job = self._make_test_job(input_images=None)
        rules = self._make_minimal_rules_without_input_images()

        # Should not raise - standard text-to-image flow
        result = await ImgGenArgsFactory.make_args_for_model(
            model_rules=rules,
            img_gen_job=job,
            nb_images=1,
            model_id="test-model",
        )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_empty_input_images_list_without_rules_succeeds(self) -> None:
        """When input_images is an empty list AND INPUT_IMAGES is NOT in model rules, no error.

        An empty list should be treated the same as None.
        """
        job = self._make_test_job(input_images=[])
        rules = self._make_minimal_rules_without_input_images()

        # Should not raise - empty list is treated as no input images
        result = await ImgGenArgsFactory.make_args_for_model(
            model_rules=rules,
            img_gen_job=job,
            nb_images=1,
            model_id="test-model",
        )

        assert isinstance(result, dict)
