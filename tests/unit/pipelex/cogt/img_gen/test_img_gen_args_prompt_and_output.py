"""Tests for ImgGenArgsFactory prompt, num_images, specific, background, and output_format mappings."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background
from pipelex.cogt.img_gen.img_gen_model_rules import (
    AspectRatioTaxonomy,
    BackgroundTaxonomy,
    ImgGenArgTopic,
    ImgGenModelRules,
    InferenceTaxonomy,
    NumImagesTaxonomy,
    OutputCompressionTaxonomy,
    OutputFormatTaxonomy,
    PromptTaxonomy,
    SafetyCheckerTaxonomy,
    SpecificTaxonomy,
)
from pipelex.tools.misc.image_utils import ImageFormat
from tests.unit.pipelex.cogt.img_gen.conftest import make_img_gen_job

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestImgGenArgsPromptAndOutput:
    def test_positive_only_drops_negative_prompt_with_warning(self, mocker: MockerFixture) -> None:
        """POSITIVE_ONLY taxonomy silently drops the negative prompt and logs a warning."""
        mock_log = mocker.patch("pipelex.cogt.img_gen.img_gen_args_factory.log")

        result = ImgGenArgsFactory.make_args_from_prompt(
            prompt_taxonomy=PromptTaxonomy.POSITIVE_ONLY,
            positive_text="a red bicycle",
            negative_text="blurry, low quality",
        )

        assert result == {"prompt": "a red bicycle"}
        mock_log.warning.assert_called_once()
        warning_message = mock_log.warning.call_args.args[0]
        assert "negative prompt" in warning_message.lower()

    def test_positive_only_without_negative_does_not_warn(self, mocker: MockerFixture) -> None:
        """POSITIVE_ONLY taxonomy emits no warning when no negative prompt is provided."""
        mock_log = mocker.patch("pipelex.cogt.img_gen.img_gen_args_factory.log")

        result = ImgGenArgsFactory.make_args_from_prompt(
            prompt_taxonomy=PromptTaxonomy.POSITIVE_ONLY,
            positive_text="a red bicycle",
            negative_text=None,
        )

        assert result == {"prompt": "a red bicycle"}
        mock_log.warning.assert_not_called()

    @pytest.mark.parametrize(
        ("negative_text", "expected_args"),
        [
            (None, {"prompt": "a red bicycle"}),
            ("", {"prompt": "a red bicycle"}),
            ("blurry", {"prompt": "a red bicycle", "negative_prompt": "blurry"}),
        ],
    )
    def test_with_negative_emits_negative_prompt_only_when_set(self, negative_text: str | None, expected_args: dict[str, Any]) -> None:
        """WITH_NEGATIVE taxonomy includes `negative_prompt` only when negative text is non-empty."""
        result = ImgGenArgsFactory.make_args_from_prompt(
            prompt_taxonomy=PromptTaxonomy.WITH_NEGATIVE,
            positive_text="a red bicycle",
            negative_text=negative_text,
        )

        assert result == expected_args

    @pytest.mark.parametrize(
        ("num_images_taxonomy", "expected_args"),
        [
            (NumImagesTaxonomy.FAL, {"num_images": 3}),
            (NumImagesTaxonomy.GPT_IMAGE, {"n": 3}),
        ],
    )
    def test_num_images_maps_to_provider_parameter_name(self, num_images_taxonomy: NumImagesTaxonomy, expected_args: dict[str, Any]) -> None:
        """FAL uses `num_images` while GPT Image uses `n` for the image count."""
        result = ImgGenArgsFactory.make_args_from_num_images(
            num_images_taxonomy=num_images_taxonomy,
            nb_images=3,
        )

        assert result == expected_args

    def test_specific_fal_disables_sync_mode(self) -> None:
        """FAL specific taxonomy always emits `sync_mode = False`."""
        result = ImgGenArgsFactory.make_args_from_specific(specific_taxonomy=SpecificTaxonomy.FAL)

        assert result == {"sync_mode": False}

    @pytest.mark.parametrize(
        ("background", "expected_value"),
        [
            (Background.TRANSPARENT, "transparent"),
            (Background.OPAQUE, "opaque"),
            (Background.AUTO, "auto"),
        ],
    )
    def test_background_available_emits_background_value(self, background: Background, expected_value: str) -> None:
        """AVAILABLE background taxonomy forwards the background value as-is."""
        result = ImgGenArgsFactory.make_args_from_background(
            background_taxonomy=BackgroundTaxonomy.AVAILABLE,
            background=background,
            model_name="gpt-image-1",
        )

        assert result == {"background": expected_value}

    def test_background_unavailable_transparent_raises_with_model_name(self) -> None:
        """UNAVAILABLE background taxonomy rejects transparent backgrounds and names the model."""
        with pytest.raises(ImgGenParameterError) as exc_info:
            ImgGenArgsFactory.make_args_from_background(
                background_taxonomy=BackgroundTaxonomy.UNAVAILABLE,
                background=Background.TRANSPARENT,
                model_name="flux-dev",
            )

        error_message = str(exc_info.value)
        assert "flux-dev" in error_message
        assert "transparent background" in error_message

    @pytest.mark.parametrize(
        "background",
        [
            Background.OPAQUE,
            Background.AUTO,
        ],
    )
    def test_background_unavailable_non_transparent_emits_nothing(self, background: Background) -> None:
        """UNAVAILABLE background taxonomy skips the parameter for non-transparent backgrounds."""
        result = ImgGenArgsFactory.make_args_from_background(
            background_taxonomy=BackgroundTaxonomy.UNAVAILABLE,
            background=background,
            model_name="flux-dev",
        )

        assert result == {}

    @pytest.mark.parametrize(
        ("output_format", "expected_value"),
        [
            (ImageFormat.PNG, "png"),
            (ImageFormat.JPEG, "jpeg"),
        ],
    )
    def test_output_format_sdxl_uses_format_key(self, output_format: ImageFormat, expected_value: str) -> None:
        """SDXL taxonomy emits png/jpeg under the `format` key."""
        result = ImgGenArgsFactory.make_args_from_output_format(
            output_format_taxonomy=OutputFormatTaxonomy.SDXL,
            output_format=output_format,
        )

        assert result == {"format": expected_value}

    def test_output_format_sdxl_rejects_webp(self) -> None:
        """SDXL taxonomy rejects WebP output and names SDXL in the error."""
        with pytest.raises(ImgGenParameterError) as exc_info:
            ImgGenArgsFactory.make_args_from_output_format(
                output_format_taxonomy=OutputFormatTaxonomy.SDXL,
                output_format=ImageFormat.WEBP,
            )

        assert "SDXL" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("output_format", "expected_value"),
        [
            (ImageFormat.PNG, "png"),
            (ImageFormat.JPEG, "jpeg"),
        ],
    )
    def test_output_format_flux_1_uses_output_format_key(self, output_format: ImageFormat, expected_value: str) -> None:
        """Flux 1 taxonomy emits png/jpeg under the `output_format` key."""
        result = ImgGenArgsFactory.make_args_from_output_format(
            output_format_taxonomy=OutputFormatTaxonomy.FLUX_1,
            output_format=output_format,
        )

        assert result == {"output_format": expected_value}

    def test_output_format_flux_1_rejects_webp(self) -> None:
        """Flux 1 taxonomy rejects WebP output and names Flux 1 in the error."""
        with pytest.raises(ImgGenParameterError) as exc_info:
            ImgGenArgsFactory.make_args_from_output_format(
                output_format_taxonomy=OutputFormatTaxonomy.FLUX_1,
                output_format=ImageFormat.WEBP,
            )

        assert "Flux 1" in str(exc_info.value)

    @pytest.mark.parametrize(
        "output_format_taxonomy",
        [
            OutputFormatTaxonomy.FLUX_2,
            OutputFormatTaxonomy.GPT_IMAGE_LEGACY,
        ],
    )
    @pytest.mark.parametrize(
        "output_format",
        [
            ImageFormat.PNG,
            ImageFormat.JPEG,
            ImageFormat.WEBP,
        ],
    )
    def test_output_format_passthrough_taxonomies_accept_all_formats(
        self,
        output_format_taxonomy: OutputFormatTaxonomy,
        output_format: ImageFormat,
    ) -> None:
        """Flux 2 and legacy GPT Image taxonomies pass every image format through, including WebP."""
        result = ImgGenArgsFactory.make_args_from_output_format(
            output_format_taxonomy=output_format_taxonomy,
            output_format=output_format,
        )

        assert result == {"output_format": output_format.value}

    @pytest.mark.asyncio
    async def test_full_fal_flux_job_builds_complete_args_dict(self) -> None:
        """A full FAL Flux rule set dispatches every topic and assembles the complete args dict."""
        model_rules: ImgGenModelRules = {
            ImgGenArgTopic.PROMPT: PromptTaxonomy.WITH_NEGATIVE,
            ImgGenArgTopic.NUM_IMAGES: NumImagesTaxonomy.FAL,
            ImgGenArgTopic.ASPECT_RATIO: AspectRatioTaxonomy.FLUX,
            ImgGenArgTopic.BACKGROUND: BackgroundTaxonomy.UNAVAILABLE,
            ImgGenArgTopic.INFERENCE: InferenceTaxonomy.FLUX,
            ImgGenArgTopic.SAFETY_CHECKER: SafetyCheckerTaxonomy.AVAILABLE,
            ImgGenArgTopic.OUTPUT_FORMAT: OutputFormatTaxonomy.FLUX_1,
            ImgGenArgTopic.OUTPUT_COMPRESSION: OutputCompressionTaxonomy.UNAVAILABLE,
            ImgGenArgTopic.SPECIFIC: SpecificTaxonomy.FAL,
        }
        img_gen_job = make_img_gen_job(
            negative_text="blurry",
            aspect_ratio=AspectRatio.LANDSCAPE_16_9,
            nb_steps=20,
            guidance_scale=3.5,
            is_moderated=False,
            safety_tolerance=2,
            output_format=ImageFormat.JPEG,
        )

        result = await ImgGenArgsFactory.make_args_for_model(
            model_rules=model_rules,
            img_gen_job=img_gen_job,
            nb_images=2,
            model_id="fal-ai/flux/dev",
            model_name="flux-dev",
        )

        assert result == {
            "prompt": "A test prompt",
            "negative_prompt": "blurry",
            "num_images": 2,
            "image_size": "landscape_16_9",
            "num_inference_steps": 20,
            "guidance_scale": 3.5,
            "enable_safety_checker": False,
            "safety_tolerance": 2,
            "output_format": "jpeg",
            "sync_mode": False,
        }
