import pytest

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio
from pipelex.plugins.google.google_img_gen_factory import (
    GoogleAspectRatioType,
    GoogleImageGenModel,
    GoogleImageSize,
    GoogleImgGenFactory,
)

BANNER_ASPECT_RATIOS = [
    AspectRatio.LANDSCAPE_4_1,
    AspectRatio.LANDSCAPE_8_1,
    AspectRatio.PORTRAIT_1_4,
    AspectRatio.PORTRAIT_1_8,
]


class TestGoogleImgGenFactory:
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
    def test_aspect_ratio_literal_mapping(self, aspect_ratio: AspectRatio, expected_literal: GoogleAspectRatioType) -> None:
        """The enum maps to Google's ratio string format, including the banner ratios."""
        assert GoogleImgGenFactory.aspect_ratio_literal(aspect_ratio) == expected_literal

    def test_aspect_ratio_literal_rejects_portrait_9_21(self) -> None:
        """9:21 is not offered by any Google Gemini Image model."""
        with pytest.raises(ImgGenParameterError, match="not supported by Google Gemini Image models"):
            GoogleImgGenFactory.aspect_ratio_literal(AspectRatio.PORTRAIT_9_21)

    def test_gemini_3_grids_are_consistent(self) -> None:
        """All Gemini 3 size grids cover the same ratio set, and the Pro subset is contained in it."""
        ratio_sets = [set(grid) for grid in GoogleImgGenFactory.SIZE_TO_ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3.values()]
        assert all(ratio_set == ratio_sets[0] for ratio_set in ratio_sets)
        assert ratio_sets[0] >= GoogleImgGenFactory.GEMINI_3_PRO_ASPECT_RATIOS
        assert set(GoogleImgGenFactory.ASPECT_RATIO_TO_DIMENSIONS_GEMINI_2_5_1K) == GoogleImgGenFactory.GEMINI_3_PRO_ASPECT_RATIOS

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
    def test_nano_banana_2_dimensions(
        self,
        aspect_ratio: AspectRatio,
        size: GoogleImageSize,
        expected_dimensions: tuple[int, int],
    ) -> None:
        """nano-banana-2 supports the full Gemini 3 grid, banners included, at every size."""
        dimensions = GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size(
            GoogleImageGenModel.NANO_BANANA_2,
            aspect_ratio=aspect_ratio,
            size=size,
        )
        assert dimensions == expected_dimensions

    @pytest.mark.parametrize("aspect_ratio", BANNER_ASPECT_RATIOS)
    def test_nano_banana_pro_rejects_banner_ratios(self, aspect_ratio: AspectRatio) -> None:
        """Gemini 3 Pro publishes no banner ratios, so nano-banana-pro rejects them cleanly."""
        with pytest.raises(ImgGenParameterError, match="not supported by model"):
            GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size(
                GoogleImageGenModel.NANO_BANANA_PRO,
                aspect_ratio=aspect_ratio,
                size="1K",
            )

    @pytest.mark.parametrize(
        ("aspect_ratio", "size", "expected_dimensions"),
        [
            (AspectRatio.SQUARE, "2K", (2048, 2048)),
            (AspectRatio.PORTRAIT_2_3, "4K", (3392, 5056)),
            (AspectRatio.LANDSCAPE_21_9, "1K", (1584, 672)),
        ],
    )
    def test_nano_banana_pro_standard_ratios_still_work(
        self,
        aspect_ratio: AspectRatio,
        size: GoogleImageSize,
        expected_dimensions: tuple[int, int],
    ) -> None:
        """nano-banana-pro keeps its standard-ratio coverage at every size after the grid restructure."""
        dimensions = GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size(
            GoogleImageGenModel.NANO_BANANA_PRO,
            aspect_ratio=aspect_ratio,
            size=size,
        )
        assert dimensions == expected_dimensions

    @pytest.mark.parametrize("aspect_ratio", BANNER_ASPECT_RATIOS)
    def test_nano_banana_rejects_banner_ratios(self, aspect_ratio: AspectRatio) -> None:
        """The Gemini 2.5 grid has no banner ratios, so nano-banana rejects them cleanly."""
        with pytest.raises(ImgGenParameterError, match="not supported by model"):
            GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size(
                GoogleImageGenModel.NANO_BANANA,
                aspect_ratio=aspect_ratio,
                size="1K",
            )

    def test_nano_banana_rejects_non_1k_size(self) -> None:
        """nano-banana only supports the 1K size."""
        with pytest.raises(ImgGenParameterError, match="only supports 1K"):
            GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size(
                GoogleImageGenModel.NANO_BANANA,
                aspect_ratio=AspectRatio.SQUARE,
                size="2K",
            )

    @pytest.mark.parametrize("size", ["2K", "4K"])
    def test_nano_banana_2_lite_rejects_non_1k_sizes(self, size: GoogleImageSize) -> None:
        """nano-banana-2-lite only supports the 1K size."""
        with pytest.raises(ImgGenParameterError, match="only supports 1K"):
            GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size(
                GoogleImageGenModel.NANO_BANANA_2_LITE,
                aspect_ratio=AspectRatio.SQUARE,
                size=size,
            )

    @pytest.mark.parametrize(
        ("aspect_ratio", "expected_dimensions"),
        [
            (AspectRatio.LANDSCAPE_4_1, (2048, 512)),
            (AspectRatio.PORTRAIT_1_8, (384, 3072)),
            (AspectRatio.SQUARE, (1024, 1024)),
        ],
    )
    def test_nano_banana_2_lite_full_ratio_set_at_1k(self, aspect_ratio: AspectRatio, expected_dimensions: tuple[int, int]) -> None:
        """nano-banana-2-lite supports the full Gemini 3 ratio set, banners included, at 1K."""
        dimensions = GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size(
            GoogleImageGenModel.NANO_BANANA_2_LITE,
            aspect_ratio=aspect_ratio,
            size="1K",
        )
        assert dimensions == expected_dimensions

    @pytest.mark.parametrize("model", list(GoogleImageGenModel))
    def test_portrait_9_21_rejected_for_every_model(self, model: GoogleImageGenModel) -> None:
        """9:21 is rejected before any per-model gating."""
        with pytest.raises(ImgGenParameterError, match="not supported by Google Gemini Image models"):
            GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size(
                model,
                aspect_ratio=AspectRatio.PORTRAIT_9_21,
                size="1K",
            )

    def test_unknown_model_rejected(self) -> None:
        """A model handle outside the Google image-gen roster is rejected."""
        with pytest.raises(ImgGenParameterError, match="not supported by Google Gemini Image Gen"):
            GoogleImgGenFactory.dimensions_for_aspect_ratio_and_size(
                "imagen-42",
                aspect_ratio=AspectRatio.SQUARE,
                size="1K",
            )
