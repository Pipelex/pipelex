"""Wire-value mappings for the Gemini Image taxonomy family.

Keyed by the `AspectRatioTaxonomy` members `GEMINI_2_5` / `GEMINI_3_PRO` / `GEMINI_3_FLASH` /
`GEMINI_3_FLASH_LITE` — a `cogt`-owned enum — so this lives beside the args factory that
consumes it rather than in the Google adapter. The native Google worker and the Pipelex
gateway (one Portkey SDK spanning several vendors' taxonomies) both resolve geometry through
it, which is why the mapping cannot belong to either adapter.

Reference: https://ai.google.dev/gemini-api/docs/image-generation
"""

import math
import operator
from collections.abc import Mapping
from typing import ClassVar, Literal, NamedTuple

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, SizeTier
from pipelex.cogt.img_gen.img_gen_model_rules import AspectRatioTaxonomy, ImgGenArgTopic
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec

GeminiAspectRatioType = Literal["1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"]

GeminiImageSize = Literal["1K", "2K", "4K"]

AspectRatioToDimensions = dict[GeminiAspectRatioType, tuple[int, int]]


class ResolvedGeminiImageConfig(NamedTuple):
    """Wire-ready Google `image_config` values plus the grid dimensions they map to.

    An `image_size` of None means the parameter must be omitted on the wire so the
    provider applies its own default (the 1K class) — never send a made-up value.
    """

    aspect_ratio: GeminiAspectRatioType
    image_size: GeminiImageSize | None
    width: int
    height: int


class ImgGenGeminiMapping:
    """Aspect-ratio and size mappings for the Gemini Image models.

    Dimension tables mirror the resolution grids Google publishes per model generation.
    Which sizes and aspect ratios each model accepts is keyed by its deck-rules
    `AspectRatioTaxonomy` value (gemini_2_5 / gemini_3_pro / gemini_3_flash /
    gemini_3_flash_lite) — model handles are deck config, not code constants.
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
    SIZE_TO_ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3: ClassVar[dict[GeminiImageSize, AspectRatioToDimensions]] = {
        "1K": ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3_1K,
        "2K": ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3_2K,
        "4K": ASPECT_RATIO_TO_DIMENSIONS_GEMINI_3_4K,
    }

    # Gemini 3 Pro Image publishes only the standard ratios — no 1:4/4:1/1:8/8:1 banners.
    GEMINI_3_PRO_ASPECT_RATIOS: ClassVar[frozenset[GeminiAspectRatioType]] = frozenset(
        ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
    )

    @classmethod
    def img_gen_taxonomy(cls, inference_model: InferenceModelSpec) -> AspectRatioTaxonomy:
        """Resolve the model's geometry taxonomy from its deck rules.

        Raises:
            ImgGenParameterError: If the model has no `aspect_ratio` rules configured
                or the configured taxonomy value is unknown.
        """
        rules = inference_model.rules or {}
        taxonomy_value = rules.get(ImgGenArgTopic.ASPECT_RATIO)
        if taxonomy_value is None:
            msg = (
                f"Google image model '{inference_model.name}' has no 'aspect_ratio' rules configured; "
                f"set rules.aspect_ratio to a Gemini taxonomy (e.g. 'gemini_3_flash')"
            )
            raise ImgGenParameterError(msg)
        try:
            return AspectRatioTaxonomy(taxonomy_value)
        except ValueError as exc:
            msg = f"Google image model '{inference_model.name}' has an unknown aspect_ratio taxonomy '{taxonomy_value}'"
            raise ImgGenParameterError(msg) from exc

    @classmethod
    def optional_img_gen_taxonomy(cls, inference_model: InferenceModelSpec) -> AspectRatioTaxonomy | None:
        """The model's geometry taxonomy, or None when rules are missing or carry an unknown value.

        The None arm mirrors the support-layer abstain policy for remotely-fetched specs (the
        Pipelex gateway catalog) whose taxonomy strings may predate this factory: with nothing
        to validate against, callers keep their pre-taxonomy behavior instead of hard-failing.
        """
        rules = inference_model.rules or {}
        taxonomy_value = rules.get(ImgGenArgTopic.ASPECT_RATIO)
        if taxonomy_value is None:
            return None
        try:
            return AspectRatioTaxonomy(taxonomy_value)
        except ValueError:
            return None

    @classmethod
    def resolve_image_config(
        cls,
        taxonomy: AspectRatioTaxonomy,
        *,
        aspect_ratio: AspectRatio,
        size: SizeTier | ImageSize | None,
        model_name: str,
    ) -> ResolvedGeminiImageConfig:
        """Resolve the wire-ready (aspect_ratio, image_size) pair and its grid dimensions.

        An exact size derives its grid cell from the taxonomy's grids and ignores the
        `aspect_ratio` argument (the two are mutually exclusive upstream). A tier maps to
        Google's `image_size` token, validated against the grids. When no size is set,
        `image_size` is None (omit the param; provider default is the 1K class) and the
        dimensions come from the 1K grid.

        Raises:
            ImgGenParameterError: If the (aspect_ratio, size) request has no cell in the
                taxonomy's grids.
        """
        if isinstance(size, ImageSize):
            ratio_literal, google_size = cls.derive_ratio_and_size_from_exact_size(taxonomy, exact_size=size, model_name=model_name)
            return ResolvedGeminiImageConfig(aspect_ratio=ratio_literal, image_size=google_size, width=size.width, height=size.height)
        image_size = cls.image_size_for_tier(size) if size is not None else None
        width, height = cls.dimensions_for_aspect_ratio_and_size(
            taxonomy,
            aspect_ratio=aspect_ratio,
            size=image_size or "1K",
            model_name=model_name,
        )
        return ResolvedGeminiImageConfig(aspect_ratio=cls.aspect_ratio_literal(aspect_ratio), image_size=image_size, width=width, height=height)

    @classmethod
    def aspect_ratio_literal(cls, aspect_ratio: AspectRatio) -> GeminiAspectRatioType:
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
    def image_size_for_tier(cls, tier: SizeTier) -> GeminiImageSize:
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
    def grids_for_taxonomy(cls, taxonomy: AspectRatioTaxonomy, *, model_name: str) -> Mapping[GeminiImageSize, AspectRatioToDimensions]:
        """The (size -> ratio -> dimensions) cells a Google taxonomy accepts, ratio-filtered.

        The returned mapping shares the class-level grid tables — read-only by contract.
        """
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
        size: GeminiImageSize,
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
    ) -> tuple[GeminiAspectRatioType, GeminiImageSize]:
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
