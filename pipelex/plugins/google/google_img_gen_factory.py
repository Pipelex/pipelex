from typing import ClassVar, Literal

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio
from pipelex.types import StrEnum

GoogleAspectRatioType = Literal["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]

GoogleImageSize = Literal["1K", "2K", "4K"]

AspectRatioToDimensions = dict[GoogleAspectRatioType, tuple[int, int]]


class GoogleImageGenModel(StrEnum):
    NANO_BANANA = "nano-banana"
    NANO_BANANA_PRO = "nano-banana-pro"
    NANO_BANANA_2 = "nano-banana-2"
    NANO_BANANA_2_LITE = "nano-banana-2-lite"


class GoogleImgGenFactory:
    """Factory class for Google image generation parameter mappings."""

    # Resolution mappings for Gemini 2.5 Flash Image (Nano Banana) - only supports 1K
    # Reference: https://ai.google.dev/gemini-api/docs/image-generation
    ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_1K: ClassVar[AspectRatioToDimensions] = {
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

    # Resolution mappings for Gemini 3.0 Pro Image (Nano Banana Pro) - supports 1K, 2K, 4K.
    # Gemini 3.1 Flash Image (Nano Banana 2) publishes identical 1K/2K/4K dimensions, and
    # Gemini 3.1 Flash Lite Image (Nano Banana 2 Lite) the same 1K dimensions (1K only).
    # Reference: https://ai.google.dev/gemini-api/docs/image-generation
    ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_PRO_1K: ClassVar[AspectRatioToDimensions] = {
        "1:1": (1024, 1024),
        "2:3": (848, 1264),
        "3:2": (1264, 848),
        "3:4": (896, 1200),
        "4:3": (1200, 896),
        "4:5": (928, 1152),
        "5:4": (1152, 928),
        "9:16": (768, 1376),
        "16:9": (1376, 768),
        "21:9": (1584, 672),
    }
    ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_PRO_2K: ClassVar[AspectRatioToDimensions] = {
        "1:1": (2048, 2048),
        "2:3": (1696, 2528),
        "3:2": (2528, 1696),
        "3:4": (1792, 2400),
        "4:3": (2400, 1792),
        "4:5": (1856, 2304),
        "5:4": (2304, 1856),
        "9:16": (1536, 2752),
        "16:9": (2752, 1536),
        "21:9": (3168, 1344),
    }
    ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_PRO_4K: ClassVar[AspectRatioToDimensions] = {
        "1:1": (4096, 4096),
        "2:3": (3392, 5056),
        "3:2": (5056, 3392),
        "3:4": (3584, 4800),
        "4:3": (4800, 3584),
        "4:5": (3712, 4608),
        "5:4": (4608, 3712),
        "9:16": (3072, 5504),
        "16:9": (5504, 3072),
        "21:9": (6336, 2688),
    }
    SIZE_TO_ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_PRO: ClassVar[dict[GoogleImageSize, AspectRatioToDimensions]] = {
        "1K": ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_PRO_1K,
        "2K": ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_PRO_2K,
        "4K": ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_PRO_4K,
    }

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
            case AspectRatio.PORTRAIT_3_4:
                return "3:4"
            case AspectRatio.PORTRAIT_2_3:
                return "2:3"
            case AspectRatio.PORTRAIT_9_16:
                return "9:16"
            case AspectRatio.PORTRAIT_9_21:
                msg = f"Aspect ratio '{aspect_ratio}' is not supported by Google Gemini Image models"
                raise ImgGenParameterError(msg)

    @classmethod
    def dimensions_for_aspect_ratio_and_size(cls, model: str, *, aspect_ratio: AspectRatio, size: GoogleImageSize) -> tuple[int, int]:
        """Get pixel dimensions (width, height) for the given aspect ratio."""
        aspect_ratio_str = cls.aspect_ratio_literal(aspect_ratio)
        match model:
            case GoogleImageGenModel.NANO_BANANA:
                if size != "1K":
                    msg = f"Model '{model}' only supports 1K size"
                    raise ImgGenParameterError(msg)
                return cls.ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_1K[aspect_ratio_str]
            case GoogleImageGenModel.NANO_BANANA_2_LITE:
                if size != "1K":
                    msg = f"Model '{model}' only supports 1K size"
                    raise ImgGenParameterError(msg)
                return cls.ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_PRO_1K[aspect_ratio_str]
            case GoogleImageGenModel.NANO_BANANA_PRO | GoogleImageGenModel.NANO_BANANA_2:
                return cls.SIZE_TO_ASPECT_RATIO_TO_DIMENSIONS_NANO_BANANA_PRO[size][aspect_ratio_str]
            case _:
                msg = f"Model '{model}' is not supported by Google Gemini Image Gen"
                raise ImgGenParameterError(msg)
