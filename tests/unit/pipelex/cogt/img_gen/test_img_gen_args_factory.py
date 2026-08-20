"""Tests for ImgGenArgsFactory input images validation.

Verifies that input images are properly validated when the model rules
don't include INPUT_IMAGES topic - preventing silent degradation to text-to-image.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import openai
import pytest

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageUri
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job import ImgGenJob
from pipelex.cogt.img_gen.img_gen_job_components import (
    AspectRatio,
    Background,
    ImgGenJobConfig,
    ImgGenJobParams,
    ImgGenJobReport,
    InputFidelity,
    Quality,
)
from pipelex.cogt.img_gen.img_gen_model_rules import (
    AspectRatioTaxonomy,
    BackgroundTaxonomy,
    ImgGenArgTopic,
    ImgGenModelRules,
    InferenceTaxonomy,
    InputFidelityTaxonomy,
    InputImagesTaxonomy,
    ModelChoiceTaxonomy,
    NumImagesTaxonomy,
    OutputCompressionTaxonomy,
    OutputFormatTaxonomy,
    PromptTaxonomy,
    SafetyCheckerTaxonomy,
)
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.providers.openai.openai_img_gen_worker import OpenAIImgGenWorker
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.tools.misc.filetype_utils import FileType
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tools.uri.prepared_file import PreparedFileBase64

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestImgGenArgsFactory:
    """Tests for ImgGenArgsFactory.make_args_for_model validation of input images."""

    @staticmethod
    def _make_test_job(
        input_images: list[PromptImage] | None = None,
        aspect_ratio: AspectRatio = AspectRatio.SQUARE,
        size: ImageSize | None = None,
        input_fidelity: InputFidelity | None = None,
        output_format: ImageFormat | None = ImageFormat.PNG,
    ) -> ImgGenJob:
        """Create a test ImgGenJob with optional input images."""
        return ImgGenJob(
            img_gen_prompt=ImgGenPrompt(
                positive_text="A test prompt",
                input_images=input_images,
            ),
            job_params=ImgGenJobParams(
                aspect_ratio=aspect_ratio,
                size=size,
                background=Background.OPAQUE,
                input_fidelity=input_fidelity,
                output_format=output_format,
            ),
            job_config=ImgGenJobConfig(is_sync_mode=False),
            job_report=ImgGenJobReport(),
            job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", user_id="test-user", pipeline_run_id="test-run")),
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
                model_name="test-model",
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
            model_name="test-model",
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
            model_name="test-model",
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
            model_name="test-model",
        )

        assert isinstance(result, dict)

    @staticmethod
    def _make_gpt_image_2_rules() -> ImgGenModelRules:
        return {
            ImgGenArgTopic.MODEL_CHOICE: ModelChoiceTaxonomy.MODEL_ID,
            ImgGenArgTopic.PROMPT: PromptTaxonomy.POSITIVE_ONLY,
            ImgGenArgTopic.NUM_IMAGES: NumImagesTaxonomy.GPT_IMAGE,
            ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GPT_IMAGE_2,
            ImgGenArgTopic.BACKGROUND: BackgroundTaxonomy.UNAVAILABLE,
            ImgGenArgTopic.INFERENCE: InferenceTaxonomy.GPT_IMAGE,
            ImgGenArgTopic.SAFETY_CHECKER: SafetyCheckerTaxonomy.UNAVAILABLE,
            ImgGenArgTopic.OUTPUT_FORMAT: OutputFormatTaxonomy.UNAVAILABLE,
            ImgGenArgTopic.INPUT_IMAGES: InputImagesTaxonomy.GPT_IMAGE,
            ImgGenArgTopic.INPUT_FIDELITY: InputFidelityTaxonomy.UNAVAILABLE,
        }

    @staticmethod
    def _make_legacy_openai_rules() -> ImgGenModelRules:
        return {
            ImgGenArgTopic.PROMPT: PromptTaxonomy.POSITIVE_ONLY,
            ImgGenArgTopic.NUM_IMAGES: NumImagesTaxonomy.GPT_IMAGE,
            ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GPT_IMAGE_LEGACY,
            ImgGenArgTopic.BACKGROUND: BackgroundTaxonomy.AVAILABLE,
            ImgGenArgTopic.INFERENCE: InferenceTaxonomy.GPT_IMAGE,
            ImgGenArgTopic.SAFETY_CHECKER: SafetyCheckerTaxonomy.OPENAI_MODERATION,
            ImgGenArgTopic.OUTPUT_FORMAT: OutputFormatTaxonomy.GPT_IMAGE_LEGACY,
            ImgGenArgTopic.INPUT_FIDELITY: InputFidelityTaxonomy.GPT_IMAGE_LEGACY,
        }

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "size",
        [
            ImageSize(width=1024, height=1024),
            ImageSize(width=1024, height=1536),
            ImageSize(width=1536, height=1024),
            ImageSize(width=2560, height=1440),
            ImageSize(width=3824, height=2144),
        ],
    )
    async def test_gpt_image_2_accepts_valid_exact_sizes(self, size: ImageSize) -> None:
        result = await ImgGenArgsFactory.make_args_for_model(
            model_rules=self._make_gpt_image_2_rules(),
            img_gen_job=self._make_test_job(size=size),
            nb_images=1,
            model_id="gpt-image-2",
            model_name="gpt-image-2",
        )

        assert result["size"] == f"{size.width}x{size.height}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("size", "expected_error"),
        [
            (ImageSize(width=1025, height=1024), "multiples of 16"),
            (ImageSize(width=3840, height=2160), "less than 3840"),
            (ImageSize(width=3072, height=1008), "at most 3:1"),
            (ImageSize(width=800, height=800), "at least 655360"),
            (ImageSize(width=3824, height=2176), "at most 8294400"),
        ],
    )
    async def test_gpt_image_2_rejects_invalid_exact_sizes(self, size: ImageSize, expected_error: str) -> None:
        with pytest.raises(ImgGenParameterError) as exc_info:
            await ImgGenArgsFactory.make_args_for_model(
                model_rules=self._make_gpt_image_2_rules(),
                img_gen_job=self._make_test_job(size=size),
                nb_images=1,
                model_id="gpt-image-2",
                model_name="gpt-image-2",
            )

        assert expected_error in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_gpt_image_2_rejects_explicit_input_fidelity(self) -> None:
        with pytest.raises(ImgGenParameterError) as exc_info:
            await ImgGenArgsFactory.make_args_for_model(
                model_rules=self._make_gpt_image_2_rules(),
                img_gen_job=self._make_test_job(input_fidelity=InputFidelity.HIGH),
                nb_images=1,
                model_id="gpt-image-2",
                model_name="gpt-image-2",
            )

        error_message = str(exc_info.value)
        assert "gpt-image-2" in error_message
        assert "does not support input_fidelity" in error_message

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("aspect_ratio", "expected_size"),
        [
            (AspectRatio.SQUARE, "1024x1024"),
            (AspectRatio.LANDSCAPE_3_2, "1536x1024"),
            (AspectRatio.PORTRAIT_2_3, "1024x1536"),
        ],
    )
    async def test_legacy_openai_models_map_supported_aspect_ratios(self, aspect_ratio: AspectRatio, expected_size: str) -> None:
        result = await ImgGenArgsFactory.make_args_for_model(
            model_rules=self._make_legacy_openai_rules(),
            img_gen_job=self._make_test_job(aspect_ratio=aspect_ratio),
            nb_images=1,
            model_id="gpt-image-1",
            model_name="gpt-image-1",
        )

        assert result["size"] == expected_size

    @pytest.mark.asyncio
    async def test_legacy_openai_models_use_explicit_size_before_aspect_ratio(self) -> None:
        result = await ImgGenArgsFactory.make_args_for_model(
            model_rules=self._make_legacy_openai_rules(),
            img_gen_job=self._make_test_job(
                aspect_ratio=AspectRatio.SQUARE,
                size=ImageSize(width=1536, height=1024),
            ),
            nb_images=1,
            model_id="gpt-image-1.5",
            model_name="gpt-image-1.5",
        )

        assert result["size"] == "1536x1024"

    @pytest.mark.asyncio
    async def test_legacy_openai_models_reject_unsupported_aspect_ratio_with_model_name(self) -> None:
        with pytest.raises(ImgGenParameterError) as exc_info:
            await ImgGenArgsFactory.make_args_for_model(
                model_rules=self._make_legacy_openai_rules(),
                img_gen_job=self._make_test_job(aspect_ratio=AspectRatio.LANDSCAPE_4_3),
                nb_images=1,
                model_id="azure-gpt-image-1-mini-deployment",
                model_name="gpt-image-1-mini",
            )

        error_message = str(exc_info.value)
        assert "gpt-image-1-mini" in error_message
        assert "azure-gpt-image-1-mini-deployment" not in error_message
        assert "OpenAI image model" in error_message
        assert "GPT Image 1" not in error_message

    def test_make_args_from_output_compression_gpt_image_emits_100(self) -> None:
        """Legacy gpt-image rules emit `output_compression = 100` (max quality for JPEG/WEBP, no-op for PNG)."""
        result = ImgGenArgsFactory.make_args_from_output_compression(
            output_compression_taxonomy=OutputCompressionTaxonomy.GPT_IMAGE_LEGACY,
        )

        assert result == {"output_compression": 100}

    def test_make_args_from_output_compression_unavailable_emits_nothing(self) -> None:
        """Models without `output_compression` support skip the kwarg entirely."""
        result = ImgGenArgsFactory.make_args_from_output_compression(
            output_compression_taxonomy=OutputCompressionTaxonomy.UNAVAILABLE,
        )

        assert result == {}
        assert "output_compression" not in result

    def test_make_args_from_model_name_can_emit_pipelex_model_name(self) -> None:
        """Some gateway-style APIs expect the Pipelex model name rather than the backend model id."""
        result = ImgGenArgsFactory.make_args_from_model_name(
            model_name_taxonomy=ModelChoiceTaxonomy.MODEL_NAME,
            model_id="provider-deployment-id",
            model_name="pipelex-model-name",
        )

        assert result == {"model": "pipelex-model-name"}

    @pytest.mark.parametrize(
        "output_format_taxonomy",
        [
            OutputFormatTaxonomy.SDXL,
            OutputFormatTaxonomy.FLUX_1,
            OutputFormatTaxonomy.FLUX_2,
            OutputFormatTaxonomy.GPT_IMAGE_LEGACY,
            OutputFormatTaxonomy.UNAVAILABLE,
        ],
    )
    def test_make_args_from_output_format_returns_empty_when_none(self, output_format_taxonomy: OutputFormatTaxonomy) -> None:
        """When output_format is None, every taxonomy returns an empty dict so the provider applies its own default."""
        result = ImgGenArgsFactory.make_args_from_output_format(
            output_format_taxonomy=output_format_taxonomy,
            output_format=None,
        )

        assert result == {}
        assert "format" not in result
        assert "output_format" not in result

    @pytest.mark.asyncio
    async def test_gpt_inference_taxonomy_defaults_quality_to_medium(self) -> None:
        """When job_params.quality is None and inference taxonomy is GPT, quality defaults to 'medium'."""
        job = self._make_test_job()
        # Ensure no explicit quality on the job
        job.job_params.quality = None
        result = await ImgGenArgsFactory.make_args_for_model(
            model_rules=self._make_gpt_image_2_rules(),
            img_gen_job=job,
            nb_images=1,
            model_id="gpt-image-2",
            model_name="gpt-image-2",
        )

        assert result["quality"] == "medium"

    @pytest.mark.asyncio
    async def test_openai_direct_worker_uses_rule_generated_args(self, mocker: MockerFixture) -> None:
        openai_client = openai.AsyncOpenAI(api_key="sk-test")

        class FakeImageData:
            b64_json = "dGVzdA=="

        class FakeUsage:
            input_tokens = 1
            output_tokens = 2

        class FakeImagesResponse:
            def __init__(self) -> None:
                self.data = [FakeImageData()]
                self.output_format = "png"
                self.size = None
                self.usage = FakeUsage()

        generate_mock = mocker.AsyncMock(return_value=FakeImagesResponse())
        mocker.patch.object(openai_client.images, "generate", generate_mock)

        inference_model = InferenceModelSpec(
            backend_name="openai",
            name="gpt-image-2",
            sdk="openai_img_gen",
            model_type=ModelType.IMG_GEN,
            model_id="gpt-image-2",
            inputs=["text", "images"],
            outputs=["image"],
            costs={CostCategory.INPUT: 8, CostCategory.OUTPUT: 30},
            thinking_mode=ThinkingMode.NONE,
            max_tokens=None,
            max_prompt_images=None,
            rules=self._make_gpt_image_2_rules(),
        )
        worker = OpenAIImgGenWorker(
            sdk_instance=openai_client,
            inference_model=inference_model,
        )

        job = self._make_test_job(size=ImageSize(width=2560, height=1440))
        job.job_params.quality = Quality.HIGH
        generated_images = await worker.gen_image_list(img_gen_job=job, nb_images=2)

        generate_mock.assert_awaited_once()
        assert generate_mock.await_args is not None
        kwargs = generate_mock.await_args.kwargs
        assert kwargs["model"] == "gpt-image-2"
        assert kwargs["prompt"] == "A test prompt"
        assert kwargs["n"] == 2
        assert kwargs["size"] == "2560x1440"
        assert kwargs["quality"] == "high"
        assert "output_format" not in kwargs
        assert "background" not in kwargs
        assert generated_images[0].size == ImageSize(width=2560, height=1440)

    @pytest.mark.asyncio
    async def test_openai_edit_endpoint_strips_moderation_kwarg(self, mocker: MockerFixture) -> None:
        """When routing to images.edit (input_images present), the 'moderation' kwarg is dropped to match the SDK signature."""
        openai_client = openai.AsyncOpenAI(api_key="sk-test")

        class FakeImageData:
            b64_json = "dGVzdA=="

        class FakeUsage:
            input_tokens = 1
            output_tokens = 2

        class FakeImagesResponse:
            def __init__(self) -> None:
                self.data = [FakeImageData()]
                self.output_format = "png"
                self.size = "1024x1024"
                self.usage = FakeUsage()

        edit_mock = mocker.AsyncMock(return_value=FakeImagesResponse())
        generate_mock = mocker.AsyncMock(return_value=FakeImagesResponse())
        mocker.patch.object(openai_client.images, "edit", edit_mock)
        mocker.patch.object(openai_client.images, "generate", generate_mock)

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

        inference_model = InferenceModelSpec(
            backend_name="openai",
            name="gpt-image-1",
            sdk="openai_img_gen",
            model_type=ModelType.IMG_GEN,
            model_id="gpt-image-1",
            inputs=["text", "images"],
            outputs=["image"],
            costs={CostCategory.INPUT: 10, CostCategory.OUTPUT: 40},
            thinking_mode=ThinkingMode.NONE,
            max_tokens=None,
            max_prompt_images=None,
            rules={
                ImgGenArgTopic.MODEL_CHOICE: ModelChoiceTaxonomy.MODEL_ID,
                ImgGenArgTopic.PROMPT: PromptTaxonomy.POSITIVE_ONLY,
                ImgGenArgTopic.NUM_IMAGES: NumImagesTaxonomy.GPT_IMAGE,
                ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.GPT_IMAGE_LEGACY,
                ImgGenArgTopic.BACKGROUND: BackgroundTaxonomy.AVAILABLE,
                ImgGenArgTopic.INFERENCE: InferenceTaxonomy.GPT_IMAGE,
                ImgGenArgTopic.SAFETY_CHECKER: SafetyCheckerTaxonomy.OPENAI_MODERATION,
                ImgGenArgTopic.OUTPUT_FORMAT: OutputFormatTaxonomy.GPT_IMAGE_LEGACY,
                ImgGenArgTopic.INPUT_IMAGES: InputImagesTaxonomy.GPT_IMAGE,
                ImgGenArgTopic.INPUT_FIDELITY: InputFidelityTaxonomy.GPT_IMAGE_LEGACY,
            },
        )
        worker = OpenAIImgGenWorker(
            sdk_instance=openai_client,
            inference_model=inference_model,
        )

        input_images = cast("list[PromptImage]", [PromptImageUri(uri="https://example.com/image.png")])
        job = self._make_test_job(input_images=input_images)
        job.job_params.is_moderated = True

        await worker.gen_image_list(img_gen_job=job, nb_images=1)

        edit_mock.assert_awaited_once()
        generate_mock.assert_not_awaited()
        assert edit_mock.await_args is not None
        kwargs = edit_mock.await_args.kwargs
        assert "moderation" not in kwargs
