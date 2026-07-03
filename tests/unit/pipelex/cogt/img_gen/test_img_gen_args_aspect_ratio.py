"""Tests for ImgGenArgsFactory.make_args_from_aspect_ratio across the FAL/Flux/Qwen taxonomies."""

from __future__ import annotations

import pytest

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio
from pipelex.cogt.img_gen.img_gen_model_rules import AspectRatioTaxonomy


class TestImgGenArgsAspectRatio:
    @pytest.mark.parametrize(
        "aspect_ratio_taxonomy",
        [
            AspectRatioTaxonomy.FLUX,
            AspectRatioTaxonomy.FLUX_11_ULTRA,
            AspectRatioTaxonomy.QWEN_IMAGE,
        ],
    )
    def test_exact_size_rejected_on_preset_only_taxonomies(self, aspect_ratio_taxonomy: AspectRatioTaxonomy) -> None:
        """Taxonomies with no exact-size wire parameter must reject an exact size instead of silently dropping it."""
        with pytest.raises(ImgGenParameterError, match="does not support exact image sizes"):
            ImgGenArgsFactory.make_args_from_aspect_ratio(
                aspect_ratio_taxonomy=aspect_ratio_taxonomy,
                aspect_ratio=AspectRatio.SQUARE,
                size=ImageSize(width=2048, height=1152),
                model_name="preset-only-model",
            )

    @pytest.mark.parametrize(
        ("aspect_ratio", "expected_image_size"),
        [
            (AspectRatio.SQUARE, "square_hd"),
            (AspectRatio.LANDSCAPE_4_3, "landscape_4_3"),
            (AspectRatio.LANDSCAPE_16_9, "landscape_16_9"),
            (AspectRatio.LANDSCAPE_21_9, "landscape_21_9"),
            (AspectRatio.PORTRAIT_3_4, "portrait_4_3"),
            (AspectRatio.PORTRAIT_9_16, "portrait_16_9"),
            (AspectRatio.PORTRAIT_9_21, "portrait_21_9"),
        ],
    )
    def test_flux_maps_supported_ratios_to_image_size(self, aspect_ratio: AspectRatio, expected_image_size: str) -> None:
        """Flux taxonomy maps each supported aspect ratio to the FAL `image_size` preset string."""
        result = ImgGenArgsFactory.make_args_from_aspect_ratio(
            aspect_ratio_taxonomy=AspectRatioTaxonomy.FLUX,
            aspect_ratio=aspect_ratio,
            size=None,
            model_name="flux-dev",
        )

        assert result == {"image_size": expected_image_size}

    @pytest.mark.parametrize(
        "aspect_ratio",
        [
            AspectRatio.LANDSCAPE_3_2,
            AspectRatio.PORTRAIT_2_3,
            AspectRatio.LANDSCAPE_4_1,
            AspectRatio.LANDSCAPE_8_1,
            AspectRatio.PORTRAIT_1_4,
            AspectRatio.PORTRAIT_1_8,
        ],
    )
    def test_flux_rejects_unsupported_ratios(self, aspect_ratio: AspectRatio) -> None:
        """Flux taxonomy raises a parameter error naming Flux for unsupported ratios."""
        with pytest.raises(ImgGenParameterError) as exc_info:
            ImgGenArgsFactory.make_args_from_aspect_ratio(
                aspect_ratio_taxonomy=AspectRatioTaxonomy.FLUX,
                aspect_ratio=aspect_ratio,
                size=None,
                model_name="flux-dev",
            )

        error_message = str(exc_info.value)
        assert aspect_ratio in error_message
        assert "Flux image generation model" in error_message

    @pytest.mark.parametrize(
        ("aspect_ratio", "expected_ratio_string"),
        [
            (AspectRatio.SQUARE, "1:1"),
            (AspectRatio.LANDSCAPE_4_3, "4:3"),
            (AspectRatio.LANDSCAPE_16_9, "16:9"),
            (AspectRatio.LANDSCAPE_21_9, "21:9"),
            (AspectRatio.PORTRAIT_3_4, "3:4"),
            (AspectRatio.PORTRAIT_9_16, "9:16"),
            (AspectRatio.PORTRAIT_9_21, "9:21"),
        ],
    )
    def test_flux_11_ultra_maps_supported_ratios_to_aspect_ratio(self, aspect_ratio: AspectRatio, expected_ratio_string: str) -> None:
        """Flux-1.1 Ultra taxonomy maps each supported aspect ratio to a `aspect_ratio` ratio string."""
        result = ImgGenArgsFactory.make_args_from_aspect_ratio(
            aspect_ratio_taxonomy=AspectRatioTaxonomy.FLUX_11_ULTRA,
            aspect_ratio=aspect_ratio,
            size=None,
            model_name="flux-1.1-ultra",
        )

        assert result == {"aspect_ratio": expected_ratio_string}

    @pytest.mark.parametrize(
        "aspect_ratio",
        [
            AspectRatio.LANDSCAPE_3_2,
            AspectRatio.PORTRAIT_2_3,
            AspectRatio.LANDSCAPE_4_1,
            AspectRatio.LANDSCAPE_8_1,
            AspectRatio.PORTRAIT_1_4,
            AspectRatio.PORTRAIT_1_8,
        ],
    )
    def test_flux_11_ultra_rejects_unsupported_ratios(self, aspect_ratio: AspectRatio) -> None:
        """Flux-1.1 Ultra taxonomy raises a parameter error naming Flux-1.1 Ultra for unsupported ratios."""
        with pytest.raises(ImgGenParameterError) as exc_info:
            ImgGenArgsFactory.make_args_from_aspect_ratio(
                aspect_ratio_taxonomy=AspectRatioTaxonomy.FLUX_11_ULTRA,
                aspect_ratio=aspect_ratio,
                size=None,
                model_name="flux-1.1-ultra",
            )

        error_message = str(exc_info.value)
        assert aspect_ratio in error_message
        assert "Flux-1.1 Ultra" in error_message

    @pytest.mark.parametrize(
        ("aspect_ratio", "expected_width", "expected_height", "expected_ratio_string"),
        [
            (AspectRatio.SQUARE, 1328, 1328, "1:1"),
            (AspectRatio.LANDSCAPE_16_9, 1664, 928, "16:9"),
            (AspectRatio.PORTRAIT_9_16, 928, 1664, "9:16"),
            (AspectRatio.LANDSCAPE_4_3, 1472, 1140, "4:3"),
            (AspectRatio.PORTRAIT_3_4, 1140, 1472, "3:4"),
            (AspectRatio.LANDSCAPE_3_2, 1584, 1056, "3:2"),
            (AspectRatio.PORTRAIT_2_3, 1056, 1584, "2:3"),
        ],
    )
    def test_qwen_image_maps_supported_ratios_to_pixel_dimensions(
        self,
        aspect_ratio: AspectRatio,
        expected_width: int,
        expected_height: int,
        expected_ratio_string: str,
    ) -> None:
        """Qwen taxonomy maps each supported aspect ratio to exact width/height pixels plus a ratio string."""
        result = ImgGenArgsFactory.make_args_from_aspect_ratio(
            aspect_ratio_taxonomy=AspectRatioTaxonomy.QWEN_IMAGE,
            aspect_ratio=aspect_ratio,
            size=None,
            model_name="qwen-image",
        )

        assert result == {
            "width": expected_width,
            "height": expected_height,
            "aspect_ratio": expected_ratio_string,
        }

    @pytest.mark.parametrize(
        "aspect_ratio",
        [
            AspectRatio.LANDSCAPE_21_9,
            AspectRatio.PORTRAIT_9_21,
            AspectRatio.LANDSCAPE_4_1,
            AspectRatio.LANDSCAPE_8_1,
            AspectRatio.PORTRAIT_1_4,
            AspectRatio.PORTRAIT_1_8,
        ],
    )
    def test_qwen_image_rejects_unsupported_ratios(self, aspect_ratio: AspectRatio) -> None:
        """Qwen taxonomy raises a parameter error for ratios outside its supported set."""
        with pytest.raises(ImgGenParameterError) as exc_info:
            ImgGenArgsFactory.make_args_from_aspect_ratio(
                aspect_ratio_taxonomy=AspectRatioTaxonomy.QWEN_IMAGE,
                aspect_ratio=aspect_ratio,
                size=None,
                model_name="qwen-image",
            )

        error_message = str(exc_info.value)
        assert aspect_ratio in error_message
        assert "not supported" in error_message
