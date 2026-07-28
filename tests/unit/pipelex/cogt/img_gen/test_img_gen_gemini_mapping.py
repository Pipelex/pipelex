import pytest

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_gemini_mapping import (
    GeminiAspectRatioType,
    GeminiImageSize,
    ImgGenGeminiMapping,
)
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, SizeTier
from pipelex.cogt.img_gen.img_gen_model_rules import AspectRatioTaxonomy

BANNER_ASPECT_RATIOS = [
    AspectRatio.LANDSCAPE_4_1,
    AspectRatio.LANDSCAPE_8_1,
    AspectRatio.PORTRAIT_1_4,
    AspectRatio.PORTRAIT_1_8,
]

GEMINI_TAXONOMIES = [
    AspectRatioTaxonomy.GEMINI_2_5,
    AspectRatioTaxonomy.GEMINI_3_PRO,
    AspectRatioTaxonomy.GEMINI_3_FLASH,
    AspectRatioTaxonomy.GEMINI_3_FLASH_LITE,
]


class TestImgGenGeminiMapping:
    @pytest.mark.parametrize(
        ("aspect_ratio", "expected_literal"),
        [
            (AspectRatio.SQUARE, "1:1"),
            (AspectRatio.LANDSCAPE_4_3, "4:3"),
            (AspectRatio.LANDSCAPE_4_1, "4:1"),
            (AspectRatio.LANDSCAPE_8_1, "8:1"),
            (AspectRatio.PORTRAIT_1_4, "1:4"),
            (AspectRatio.PORTRAIT_1_8, "1:8"),
        ],
    )
    def test_aspect_ratio_literal_mapping(self, aspect_ratio: AspectRatio, expected_literal: GeminiAspectRatioType) -> None:
        """The enum maps to Google's ratio string format, including the banner ratios."""
        assert ImgGenGeminiMapping.aspect_ratio_literal(aspect_ratio) == expected_literal

    def test_aspect_ratio_literal_rejects_portrait_9_21(self) -> None:
        """9:21 is not offered by any Google Gemini Image model."""
        with pytest.raises(ImgGenParameterError, match="not supported by Google Gemini Image models"):
            ImgGenGeminiMapping.aspect_ratio_literal(AspectRatio.PORTRAIT_9_21)

    def test_gemini_3_grids_are_consistent(self) -> None:
        """All Gemini 3 size grids cover the same ratio set, and the Pro subset is contained in it."""
        ratio_sets = [set(grid) for grid in ImgGenGeminiMapping.SIZE_TO_ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3.values()]
        assert all(ratio_set == ratio_sets[0] for ratio_set in ratio_sets)
        assert ratio_sets[0] >= ImgGenGeminiMapping.GEMINI_3_PRO_ASPECT_RATIOS
        assert set(ImgGenGeminiMapping.ASPECT_RATIO_TO_DIMENSIONS_GEMINI_2_5_1K) == ImgGenGeminiMapping.GEMINI_3_PRO_ASPECT_RATIOS

    @pytest.mark.parametrize(
        ("tier", "expected_image_size"),
        [
            (SizeTier.ONE_K, "1K"),
            (SizeTier.TWO_K, "2K"),
            (SizeTier.FOUR_K, "4K"),
        ],
    )
    def test_image_size_for_tier(self, tier: SizeTier, expected_image_size: GeminiImageSize) -> None:
        """Portable size tiers map to Google's wire tokens."""
        assert ImgGenGeminiMapping.image_size_for_tier(tier) == expected_image_size

    def test_image_size_for_tier_rejects_half_k(self) -> None:
        """The 0.5k wire token is unverified — rejected until Google opens it."""
        with pytest.raises(ImgGenParameterError, match=r"0\.5k"):
            ImgGenGeminiMapping.image_size_for_tier(SizeTier.HALF_K)

    @pytest.mark.parametrize(
        ("aspect_ratio", "size", "expected_dimensions"),
        [
            (AspectRatio.LANDSCAPE_4_1, "1K", (2048, 512)),
            (AspectRatio.LANDSCAPE_4_1, "2K", (4096, 1024)),
            (AspectRatio.LANDSCAPE_4_1, "4K", (8192, 2048)),
            (AspectRatio.LANDSCAPE_8_1, "1K", (3072, 384)),
            (AspectRatio.LANDSCAPE_8_1, "2K", (6144, 768)),
            (AspectRatio.LANDSCAPE_8_1, "4K", (12288, 1536)),
            (AspectRatio.PORTRAIT_1_4, "1K", (512, 2048)),
            (AspectRatio.PORTRAIT_1_4, "2K", (1024, 4096)),
            (AspectRatio.PORTRAIT_1_4, "4K", (2048, 8192)),
            (AspectRatio.PORTRAIT_1_8, "1K", (384, 3072)),
            (AspectRatio.PORTRAIT_1_8, "2K", (768, 6144)),
            (AspectRatio.PORTRAIT_1_8, "4K", (1536, 12288)),
            (AspectRatio.SQUARE, "1K", (1024, 1024)),
            (AspectRatio.LANDSCAPE_16_9, "4K", (5504, 3072)),
        ],
    )
    def test_gemini_3_flash_dimensions(
        self,
        aspect_ratio: AspectRatio,
        size: GeminiImageSize,
        expected_dimensions: tuple[int, int],
    ) -> None:
        """gemini_3_flash supports the full Gemini 3 grid, banners included, at every size."""
        dimensions = ImgGenGeminiMapping.dimensions_for_aspect_ratio_and_size(
            AspectRatioTaxonomy.GEMINI_3_FLASH,
            aspect_ratio=aspect_ratio,
            size=size,
            model_name="nano-banana-2",
        )
        assert dimensions == expected_dimensions

    @pytest.mark.parametrize("aspect_ratio", BANNER_ASPECT_RATIOS)
    def test_gemini_3_pro_rejects_banner_ratios(self, aspect_ratio: AspectRatio) -> None:
        """Gemini 3 Pro publishes no banner ratios, so its taxonomy rejects them cleanly."""
        with pytest.raises(ImgGenParameterError, match="not supported by model"):
            ImgGenGeminiMapping.dimensions_for_aspect_ratio_and_size(
                AspectRatioTaxonomy.GEMINI_3_PRO,
                aspect_ratio=aspect_ratio,
                size="1K",
                model_name="nano-banana-pro",
            )

    @pytest.mark.parametrize(
        ("aspect_ratio", "size", "expected_dimensions"),
        [
            (AspectRatio.SQUARE, "2K", (2048, 2048)),
            (AspectRatio.PORTRAIT_2_3, "4K", (3392, 5056)),
            (AspectRatio.LANDSCAPE_21_9, "1K", (1584, 672)),
        ],
    )
    def test_gemini_3_pro_standard_ratios_work_at_every_size(
        self,
        aspect_ratio: AspectRatio,
        size: GeminiImageSize,
        expected_dimensions: tuple[int, int],
    ) -> None:
        dimensions = ImgGenGeminiMapping.dimensions_for_aspect_ratio_and_size(
            AspectRatioTaxonomy.GEMINI_3_PRO,
            aspect_ratio=aspect_ratio,
            size=size,
            model_name="nano-banana-pro",
        )
        assert dimensions == expected_dimensions

    @pytest.mark.parametrize("aspect_ratio", BANNER_ASPECT_RATIOS)
    def test_gemini_2_5_rejects_banner_ratios(self, aspect_ratio: AspectRatio) -> None:
        """The Gemini 2.5 grid has no banner ratios."""
        with pytest.raises(ImgGenParameterError, match="not supported by model"):
            ImgGenGeminiMapping.dimensions_for_aspect_ratio_and_size(
                AspectRatioTaxonomy.GEMINI_2_5,
                aspect_ratio=aspect_ratio,
                size="1K",
                model_name="nano-banana",
            )

    @pytest.mark.parametrize("size", ["2K", "4K"])
    def test_gemini_2_5_rejects_non_1k_sizes(self, size: GeminiImageSize) -> None:
        """gemini_2_5 only offers the 1K size."""
        with pytest.raises(ImgGenParameterError, match="does not support image size"):
            ImgGenGeminiMapping.dimensions_for_aspect_ratio_and_size(
                AspectRatioTaxonomy.GEMINI_2_5,
                aspect_ratio=AspectRatio.SQUARE,
                size=size,
                model_name="nano-banana",
            )

    @pytest.mark.parametrize("size", ["2K", "4K"])
    def test_gemini_3_flash_lite_rejects_non_1k_sizes(self, size: GeminiImageSize) -> None:
        """gemini_3_flash_lite only offers the 1K size."""
        with pytest.raises(ImgGenParameterError, match="does not support image size"):
            ImgGenGeminiMapping.dimensions_for_aspect_ratio_and_size(
                AspectRatioTaxonomy.GEMINI_3_FLASH_LITE,
                aspect_ratio=AspectRatio.SQUARE,
                size=size,
                model_name="nano-banana-2-lite",
            )

    @pytest.mark.parametrize(
        ("aspect_ratio", "expected_dimensions"),
        [
            (AspectRatio.LANDSCAPE_4_1, (2048, 512)),
            (AspectRatio.PORTRAIT_1_8, (384, 3072)),
            (AspectRatio.SQUARE, (1024, 1024)),
        ],
    )
    def test_gemini_3_flash_lite_full_ratio_set_at_1k(self, aspect_ratio: AspectRatio, expected_dimensions: tuple[int, int]) -> None:
        """gemini_3_flash_lite supports the full Gemini 3 ratio set, banners included, at 1K."""
        dimensions = ImgGenGeminiMapping.dimensions_for_aspect_ratio_and_size(
            AspectRatioTaxonomy.GEMINI_3_FLASH_LITE,
            aspect_ratio=aspect_ratio,
            size="1K",
            model_name="nano-banana-2-lite",
        )
        assert dimensions == expected_dimensions

    @pytest.mark.parametrize("taxonomy", GEMINI_TAXONOMIES)
    def test_portrait_9_21_rejected_for_every_taxonomy(self, taxonomy: AspectRatioTaxonomy) -> None:
        """9:21 is rejected before any per-taxonomy gating."""
        with pytest.raises(ImgGenParameterError, match="not supported by Google Gemini Image models"):
            ImgGenGeminiMapping.dimensions_for_aspect_ratio_and_size(
                taxonomy,
                aspect_ratio=AspectRatio.PORTRAIT_9_21,
                size="1K",
                model_name="some-gemini-model",
            )

    def test_non_google_taxonomy_rejected(self) -> None:
        """A non-Gemini taxonomy value has no Google resolution grids."""
        with pytest.raises(ImgGenParameterError, match="not a Google Gemini image generation taxonomy"):
            ImgGenGeminiMapping.dimensions_for_aspect_ratio_and_size(
                AspectRatioTaxonomy.FLUX,
                aspect_ratio=AspectRatio.SQUARE,
                size="1K",
                model_name="flux-dev",
            )

    @pytest.mark.parametrize(
        ("taxonomy", "exact_size", "expected_ratio", "expected_image_size"),
        [
            (AspectRatioTaxonomy.GEMINI_3_FLASH, ImageSize(width=2048, height=2048), "1:1", "2K"),
            (AspectRatioTaxonomy.GEMINI_3_FLASH, ImageSize(width=2752, height=1536), "16:9", "2K"),
            (AspectRatioTaxonomy.GEMINI_3_FLASH, ImageSize(width=5504, height=3072), "16:9", "4K"),
            (AspectRatioTaxonomy.GEMINI_3_FLASH, ImageSize(width=512, height=2048), "1:4", "1K"),
            (AspectRatioTaxonomy.GEMINI_3_PRO, ImageSize(width=2048, height=2048), "1:1", "2K"),
            (AspectRatioTaxonomy.GEMINI_2_5, ImageSize(width=1024, height=1024), "1:1", "1K"),
            (AspectRatioTaxonomy.GEMINI_3_FLASH_LITE, ImageSize(width=1024, height=1024), "1:1", "1K"),
        ],
    )
    def test_exact_grid_hit_derives_ratio_and_size(
        self,
        taxonomy: AspectRatioTaxonomy,
        exact_size: ImageSize,
        expected_ratio: GeminiAspectRatioType,
        expected_image_size: GeminiImageSize,
    ) -> None:
        """An exact WxH equal to a grid cell derives the (ratio, size) pair."""
        derived = ImgGenGeminiMapping.derive_ratio_and_size_from_exact_size(
            taxonomy,
            exact_size=exact_size,
            model_name="some-gemini-model",
        )
        assert derived == (expected_ratio, expected_image_size)

    def test_exact_grid_miss_suggests_nearest_cells(self) -> None:
        """A near-miss errors out naming the nearest valid cells — never silently snaps."""
        with pytest.raises(ImgGenParameterError) as exc_info:
            ImgGenGeminiMapping.derive_ratio_and_size_from_exact_size(
                AspectRatioTaxonomy.GEMINI_3_FLASH,
                exact_size=ImageSize(width=2000, height=2000),
                model_name="nano-banana-2",
            )
        error_message = str(exc_info.value)
        assert "2000x2000" in error_message
        assert "2048x2048" in error_message
        assert "1:1" in error_message

    def test_exact_grid_respects_taxonomy_size_gating(self) -> None:
        """A 2K cell of the Gemini 3 grid is not a hit on a 1K-only taxonomy."""
        with pytest.raises(ImgGenParameterError) as exc_info:
            ImgGenGeminiMapping.derive_ratio_and_size_from_exact_size(
                AspectRatioTaxonomy.GEMINI_3_FLASH_LITE,
                exact_size=ImageSize(width=2048, height=2048),
                model_name="nano-banana-2-lite",
            )
        error_message = str(exc_info.value)
        assert "1024x1024" in error_message

    def test_exact_grid_respects_taxonomy_ratio_gating(self) -> None:
        """A banner cell of the Gemini 3 grid is not a hit on the Pro taxonomy (no banners)."""
        with pytest.raises(ImgGenParameterError):
            ImgGenGeminiMapping.derive_ratio_and_size_from_exact_size(
                AspectRatioTaxonomy.GEMINI_3_PRO,
                exact_size=ImageSize(width=2048, height=512),
                model_name="nano-banana-pro",
            )

    @pytest.mark.parametrize(
        ("taxonomy", "aspect_ratio", "tier", "expected"),
        [
            (AspectRatioTaxonomy.GEMINI_3_FLASH, AspectRatio.SQUARE, SizeTier.TWO_K, ("1:1", "2K", 2048, 2048)),
            (AspectRatioTaxonomy.GEMINI_3_FLASH, AspectRatio.LANDSCAPE_16_9, SizeTier.FOUR_K, ("16:9", "4K", 5504, 3072)),
            (AspectRatioTaxonomy.GEMINI_2_5, AspectRatio.SQUARE, SizeTier.ONE_K, ("1:1", "1K", 1024, 1024)),
        ],
    )
    def test_resolve_image_config_from_tier(
        self,
        taxonomy: AspectRatioTaxonomy,
        aspect_ratio: AspectRatio,
        tier: SizeTier,
        expected: tuple[GeminiAspectRatioType, GeminiImageSize, int, int],
    ) -> None:
        """A tier resolves to Google's `image_size` token plus the matching grid dimensions."""
        resolved = ImgGenGeminiMapping.resolve_image_config(
            taxonomy,
            aspect_ratio=aspect_ratio,
            size=tier,
            model_name="some-gemini-model",
        )
        assert resolved == expected

    def test_resolve_image_config_unset_size_omits_wire_param(self) -> None:
        """No size set -> `image_size` stays None (param omitted on the wire), dims come from the 1K grid."""
        resolved = ImgGenGeminiMapping.resolve_image_config(
            AspectRatioTaxonomy.GEMINI_3_FLASH,
            aspect_ratio=AspectRatio.SQUARE,
            size=None,
            model_name="nano-banana-2",
        )
        assert resolved.aspect_ratio == "1:1"
        assert resolved.image_size is None
        assert (resolved.width, resolved.height) == (1024, 1024)

    def test_resolve_image_config_from_exact_size(self) -> None:
        """An exact size resolves through the grid derivation, ignoring the aspect_ratio argument."""
        resolved = ImgGenGeminiMapping.resolve_image_config(
            AspectRatioTaxonomy.GEMINI_3_FLASH,
            aspect_ratio=AspectRatio.SQUARE,
            size=ImageSize(width=2752, height=1536),
            model_name="nano-banana-2",
        )
        assert resolved == ("16:9", "2K", 2752, 1536)

    def test_resolve_image_config_rejects_tier_beyond_taxonomy(self) -> None:
        """A tier outside the taxonomy's grids is a validation error, not a silent downgrade."""
        with pytest.raises(ImgGenParameterError, match="does not support image size"):
            ImgGenGeminiMapping.resolve_image_config(
                AspectRatioTaxonomy.GEMINI_2_5,
                aspect_ratio=AspectRatio.SQUARE,
                size=SizeTier.TWO_K,
                model_name="nano-banana",
            )

    def test_resolve_image_config_rejects_half_k(self) -> None:
        with pytest.raises(ImgGenParameterError, match=r"0\.5k"):
            ImgGenGeminiMapping.resolve_image_config(
                AspectRatioTaxonomy.GEMINI_3_FLASH,
                aspect_ratio=AspectRatio.SQUARE,
                size=SizeTier.HALF_K,
                model_name="nano-banana-2",
            )
