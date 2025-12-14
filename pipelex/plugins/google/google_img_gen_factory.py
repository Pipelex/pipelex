from typing import ClassVar, Literal

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio

GoogleAspectRatioType = Literal["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]


class GoogleImgGenFactory:
    """Factory class for Google image generation parameter mappings."""

    # Resolution mappings for Gemini 2.5 Flash Image (Nano Banana)
    # Reference: https://ai.google.dev/gemini-api/docs/image-generation
    ASPECT_RATIO_TO_SIZE: ClassVar[dict[GoogleAspectRatioType, tuple[int, int]]] = {
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

    @classmethod
    def aspect_ratio_string(cls, aspect_ratio: AspectRatio) -> GoogleAspectRatioType:
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
    def image_size_for_aspect_ratio(cls, aspect_ratio: AspectRatio) -> tuple[int, int]:
        """Get pixel dimensions (width, height) for the given aspect ratio."""
        aspect_ratio_str = cls.aspect_ratio_string(aspect_ratio)
        return cls.ASPECT_RATIO_TO_SIZE[aspect_ratio_str]
