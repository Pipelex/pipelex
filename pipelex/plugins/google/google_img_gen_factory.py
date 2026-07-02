import math
import operator
from typing import ClassVar, Literal

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, SizeTier
from pipelex.cogt.img_gen.img_gen_model_rules import AspectRatioTaxonomy

GoogleAspectRatioType = Literal["1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"]

GoogleImageSize = Literal["1K", "2K", "4K"]

AspectRatioToDimensions = dict[GoogleAspectRatioType, tuple[int, int]]


class GoogleImgGenFactory:
    """Factory class for Google image generation parameter mappings.

    Dimension tables mirror the resolution grids Google publishes per model generation.
    Which sizes and aspect ratios each model accepts is keyed by its deck-rules
    `AspectRatioTaxonomy` value (gemini_2_5 / gemini_3_pro / gemini_3_flash /
    gemini_3_flash_lite) — model handles are deck config, not code constants.
    Reference: https://ai.google.dev/gemini-api/docs/image-generation
    """

    # Gemini 2.5 generation grid — used by the gemini_2_5 taxonomy (nano-banana).
    # 1K only, standard ratios only.
    ASPECT_RATIO_TO_DIMENSIONS_GEMINI_2_5_1K: ClassVar[AspectRatioToDimensions] = {
        "1:1": (1024, 1024),
        "2:3": (832, 1248),
        "3:2": (1248, 832),
        "3:4": (864, 1184),
        "4:3": (1184, 864),
        "4:5": (896, 1152),
        "5:4": (1152, 896),
        "9:16": (768, 1344),
        "16:9": (1344, 768),
        "21:9": (1536, 672),
    }

    # Gemini 3 generation grid — shared by gemini_3_pro (1K/2K/4K, standard ratios only,
    # gated by GEMINI_3_PRO_ASPECT_RATIOS), gemini_3_flash (1K/2K/4K, all ratios) and
    # gemini_3_flash_lite (1K only, all ratios). Rows follow Google's published table order.
    ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3_1K: ClassVar[AspectRatioToDimensions] = {
        "1:1": (1024, 1024),
        "1:4": (512, 2048),
        "1:8": (384, 3072),
        "2:3": (848, 1264),
        "3:2": (1264, 848),
        "3:4": (896, 1200),
        "4:1": (2048, 512),
        "4:3": (1200, 896),
        "4:5": (928, 1152),
        "5:4": (1152, 928),
        "8:1": (3072, 384),
        "9:16": (768, 1376),
        "16:9": (1376, 768),
        "21:9": (1584, 672),
    }
    ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3_2K: ClassVar[AspectRatioToDimensions] = {
        "1:1": (2048, 2048),
        "1:4": (1024, 4096),
        "1:8": (768, 6144),
        "2:3": (1696, 2528),
        "3:2": (2528, 1696),
        "3:4": (1792, 2400),
        "4:1": (4096, 1024),
        "4:3": (2400, 1792),
        "4:5": (1856, 2304),
        "5:4": (2304, 1856),
        "8:1": (6144, 768),
        "9:16": (1536, 2752),
        "16:9": (2752, 1536),
        "21:9": (3168, 1344),
    }
    ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3_4K: ClassVar[AspectRatioToDimensions] = {
        "1:1": (4096, 4096),
        "1:4": (2048, 8192),
        "1:8": (1536, 12288),
        "2:3": (3392, 5056),
        "3:2": (5056, 3392),
        "3:4": (3584, 4800),
        "4:1": (8192, 2048),
        "4:3": (4800, 3584),
        "4:5": (3712, 4608),
        "5:4": (4608, 3712),
        "8:1": (12288, 1536),
        "9:16": (3072, 5504),
        "16:9": (5504, 3072),
        "21:9": (6336, 2688),
    }
    SIZE_TO_ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3: ClassVar[dict[GoogleImageSize, AspectRatioToDimensions]] = {
        "1K": ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3_1K,
        "2K": ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3_2K,
        "4K": ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3_4K,
    }

    # Gemini 3 Pro Image publishes only the standard ratios — no 1:4/4:1/1:8/8:1 banners.
    GEMINI_3_PRO_ASPECT_RATIOS: ClassVar[frozenset[GoogleAspectRatioType]] = frozenset(
        ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
    )

    @classmethod
    def aspect_ratio_literal(cls, aspect_ratio: AspectRatio) -> GoogleAspectRatioType:
        """Map AspectRatio enum to Google's string format."""
        match aspect_ratio:
            case AspectRatio.SQUARE:
                return "1:1"
            case AspectRatio.LANDSCAPE_4_3:
                return "4:3"
            case AspectRatio.LANDSCAPE_3_2:
                return "3:2"
            case AspectRatio.LANDSCAPE_16_9:
                return "16:9"
            case AspectRatio.LANDSCAPE_21_9:
                return "21:9"
            case AspectRatio.LANDSCAPE_4_1:
                return "4:1"
            case AspectRatio.LANDSCAPE_8_1:
                return "8:1"
            case AspectRatio.PORTRAIT_3_4:
                return "3:4"
            case AspectRatio.PORTRAIT_2_3:
                return "2:3"
            case AspectRatio.PORTRAIT_9_16:
                return "9:16"
            case AspectRatio.PORTRAIT_1_4:
                return "1:4"
            case AspectRatio.PORTRAIT_1_8:
                return "1:8"
            case AspectRatio.PORTRAIT_9_21:
                msg = f"Aspect ratio '{aspect_ratio}' is not supported by Google Gemini Image models"
                raise ImgGenParameterError(msg)

    @classmethod
    def image_size_for_tier(cls, tier: SizeTier) -> GoogleImageSize:
        """Map a portable size tier to Google's `image_size` wire token."""
        match tier:
            case SizeTier.ONE_K:
                return "1K"
            case SizeTier.TWO_K:
                return "2K"
            case SizeTier.FOUR_K:
                return "4K"
            case SizeTier.HALF_K:
                msg = f"Size tier '{tier}' is not supported by Google Gemini Image models yet (no verified wire token)"
                raise ImgGenParameterError(msg)

    @classmethod
    def grids_for_taxonomy(cls, taxonomy: AspectRatioTaxonomy, *, model_name: str) -> dict[GoogleImageSize, AspectRatioToDimensions]:
        """The (size -> ratio -> dimensions) cells a Google taxonomy accepts, ratio-filtered."""
        match taxonomy:
            case AspectRatioTaxonomy.GEMINI_2_5:
                return {"1K": cls.ASPECT_RATIO_TO_DIMENSIONS_GEMINI_2_5_1K}
            case AspectRatioTaxonomy.GEMINI_3_PRO:
                return {
                    size: {ratio: dims for ratio, dims in grid.items() if ratio in cls.GEMINI_3_PRO_ASPECT_RATIOS}
                    for size, grid in cls.SIZE_TO_ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3.items()
                }
            case AspectRatioTaxonomy.GEMINI_3_FLASH:
                return cls.SIZE_TO_ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3
            case AspectRatioTaxonomy.GEMINI_3_FLASH_LITE:
                return {"1K": cls.ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3_1K}
            case (
                AspectRatioTaxonomy.FLUX
                | AspectRatioTaxonomy.FLUX_11_ULTRA
                | AspectRatioTaxonomy.GPT_IMAGE_LEGACY
                | AspectRatioTaxonomy.GPT_IMAGE_2
                | AspectRatioTaxonomy.QWEN_IMAGE
            ):
                msg = f"Taxonomy '{taxonomy}' configured for model '{model_name}' is not a Google Gemini image generation taxonomy"
                raise ImgGenParameterError(msg)

    @classmethod
    def dimensions_for_aspect_ratio_and_size(
        cls,
        taxonomy: AspectRatioTaxonomy,
        *,
        aspect_ratio: AspectRatio,
        size: GoogleImageSize,
        model_name: str,
    ) -> tuple[int, int]:
        """Get pixel dimensions (width, height) for the given aspect ratio and size, gated per taxonomy."""
        aspect_ratio_str = cls.aspect_ratio_literal(aspect_ratio)
        grids = cls.grids_for_taxonomy(taxonomy, model_name=model_name)
        grid = grids.get(size)
        if grid is None:
            supported_sizes = ", ".join(grids)
            msg = f"Model '{model_name}' does not support image size '{size}'; supported: {supported_sizes}"
            raise ImgGenParameterError(msg)
        dimensions = grid.get(aspect_ratio_str)
        if dimensions is None:
            msg = f"Aspect ratio '{aspect_ratio}' is not supported by model '{model_name}'"
            raise ImgGenParameterError(msg)
        return dimensions

    @classmethod
    def derive_ratio_and_size_from_exact_size(
        cls,
        taxonomy: AspectRatioTaxonomy,
        *,
        exact_size: ImageSize,
        model_name: str,
    ) -> tuple[GoogleAspectRatioType, GoogleImageSize]:
        """Exact-grid match: derive the (ratio, size) pair whose grid cell equals the exact WxH.

        Raises:
            ImgGenParameterError: If no cell matches — the message names the nearest valid
                cells (closest ratio, then closest area). Never silently snaps.
        """
        grids = cls.grids_for_taxonomy(taxonomy, model_name=model_name)
        for google_size, grid in grids.items():
            for ratio_str, dimensions in grid.items():
                if dimensions == (exact_size.width, exact_size.height):
                    return ratio_str, google_size

        requested_area = exact_size.width * exact_size.height
        requested_ratio = exact_size.width / exact_size.height
        candidates: list[tuple[float, int, str, str]] = []
        for google_size, grid in grids.items():
            for ratio_str, (width, height) in grid.items():
                ratio_distance = abs(math.log((width / height) / requested_ratio))
                area_distance = abs(width * height - requested_area)
                candidates.append((ratio_distance, area_distance, f"{width}x{height}", f"{ratio_str} @ {google_size}"))
        candidates.sort(key=operator.itemgetter(0, 1))
        suggestions = ", ".join(f"{dims_str} ({cell_desc})" for _, _, dims_str, cell_desc in candidates[:3])
        msg = (
            f"Exact size '{exact_size.width}x{exact_size.height}' does not match any cell of the resolution grid "
            f"of model '{model_name}'; nearest valid sizes: {suggestions}"
        )
        raise ImgGenParameterError(msg)
