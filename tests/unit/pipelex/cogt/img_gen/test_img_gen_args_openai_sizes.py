"""Tests for OpenAI size payloads in ImgGenArgsFactory: tier-derived sizes and the reliability note.

Covers the GPT_IMAGE_2 tier scaling (tier -> scaled preset -> validated `size` string), the
legacy fixed-grid path, and the reliability-boundary log demotion: tier-derived sizes above
the boundary log verbose (the tier is a portable request, not a user mistake), while
user-supplied exact sizes keep the loud warning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_args_factory import ImgGenArgsFactory
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, SizeTier
from pipelex.cogt.img_gen.img_gen_model_rules import AspectRatioTaxonomy


class TestImgGenArgsOpenAISizes:
    @pytest.mark.parametrize(
        ("aspect_ratio", "size", "expected_size_string"),
        [
            (AspectRatio.SQUARE, None, "1024x1024"),
            (AspectRatio.SQUARE, SizeTier.ONE_K, "1024x1024"),
            (AspectRatio.SQUARE, SizeTier.TWO_K, "2048x2048"),
            (AspectRatio.LANDSCAPE_16_9, SizeTier.TWO_K, "3072x1728"),
            (AspectRatio.PORTRAIT_9_16, SizeTier.TWO_K, "1728x3072"),
            (AspectRatio.LANDSCAPE_16_9, ImageSize(width=2048, height=1152), "2048x1152"),
        ],
    )
    def test_gpt_image_2_size_payload(
        self,
        aspect_ratio: AspectRatio,
        size: SizeTier | ImageSize | None,
        expected_size_string: str,
    ) -> None:
        """GPT Image 2 sends one `size` string: preset when unset, scaled preset for a tier, pass-through for exact."""
        result = ImgGenArgsFactory.make_args_from_aspect_ratio(
            aspect_ratio_taxonomy=AspectRatioTaxonomy.GPT_IMAGE_2,
            aspect_ratio=aspect_ratio,
            size=size,
            model_name="gpt-image-2",
        )

        assert result == {"size": expected_size_string}

    @pytest.mark.parametrize("tier", [SizeTier.HALF_K, SizeTier.FOUR_K])
    def test_gpt_image_2_unsatisfiable_tiers_rejected(self, tier: SizeTier) -> None:
        """Tiers whose scaled size falls outside the model's range are honest errors, not silent snaps."""
        with pytest.raises(ImgGenParameterError, match="not satisfiable"):
            ImgGenArgsFactory.make_args_from_aspect_ratio(
                aspect_ratio_taxonomy=AspectRatioTaxonomy.GPT_IMAGE_2,
                aspect_ratio=AspectRatio.SQUARE,
                size=tier,
                model_name="gpt-image-2",
            )

    def test_legacy_gpt_image_tier_1k_maps_to_fixed_size(self) -> None:
        """On the legacy fixed grid, '1k' is the grid itself: same payload as no size at all."""
        result = ImgGenArgsFactory.make_args_from_aspect_ratio(
            aspect_ratio_taxonomy=AspectRatioTaxonomy.GPT_IMAGE_LEGACY,
            aspect_ratio=AspectRatio.LANDSCAPE_3_2,
            size=SizeTier.ONE_K,
            model_name="gpt-image-1",
        )

        assert result == {"size": "1536x1024"}

    def test_legacy_gpt_image_rejects_other_tiers(self) -> None:
        with pytest.raises(ImgGenParameterError, match="only offers the '1k' class"):
            ImgGenArgsFactory.make_args_from_aspect_ratio(
                aspect_ratio_taxonomy=AspectRatioTaxonomy.GPT_IMAGE_LEGACY,
                aspect_ratio=AspectRatio.SQUARE,
                size=SizeTier.TWO_K,
                model_name="gpt-image-1",
            )

    def test_tier_derived_reliability_note_is_verbose(self, mocker: MockerFixture) -> None:
        """A tier-derived size above the reliability boundary logs verbose, not a loud warning."""
        mock_log = mocker.patch("pipelex.providers.openai.openai_img_gen_factory.log")

        ImgGenArgsFactory.make_args_from_aspect_ratio(
            aspect_ratio_taxonomy=AspectRatioTaxonomy.GPT_IMAGE_2,
            aspect_ratio=AspectRatio.SQUARE,
            size=SizeTier.TWO_K,
            model_name="gpt-image-2",
        )

        mock_log.warning.assert_not_called()
        mock_log.verbose.assert_called_once()

    def test_user_exact_size_reliability_warning_stays_loud(self, mocker: MockerFixture) -> None:
        """A user-supplied exact size above the reliability boundary keeps the loud warning."""
        mock_log = mocker.patch("pipelex.providers.openai.openai_img_gen_factory.log")

        ImgGenArgsFactory.make_args_from_aspect_ratio(
            aspect_ratio_taxonomy=AspectRatioTaxonomy.GPT_IMAGE_2,
            aspect_ratio=AspectRatio.SQUARE,
            size=ImageSize(width=2048, height=2048),
            model_name="gpt-image-2",
        )

        mock_log.warning.assert_called_once()
        mock_log.verbose.assert_not_called()

    def test_exact_size_below_reliability_boundary_logs_nothing(self, mocker: MockerFixture) -> None:
        mock_log = mocker.patch("pipelex.providers.openai.openai_img_gen_factory.log")

        ImgGenArgsFactory.make_args_from_aspect_ratio(
            aspect_ratio_taxonomy=AspectRatioTaxonomy.GPT_IMAGE_2,
            aspect_ratio=AspectRatio.LANDSCAPE_16_9,
            size=ImageSize(width=2048, height=1152),
            model_name="gpt-image-2",
        )

        mock_log.warning.assert_not_called()
        mock_log.verbose.assert_not_called()
