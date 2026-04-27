from typing import ClassVar, Literal

from openai import Omit, omit

from pipelex import log
from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, InputFidelity, Quality
from pipelex.tools.misc.image_utils import ImageFormat

OpenAIImageLegacySizeType = Literal["1024x1024", "1536x1024", "1024x1536"]
OpenAIImageOutputFormatType = Literal["png", "jpeg", "webp"]
OpenAIImageModerationType = Literal["low", "auto"] | Omit
OpenAIImageQualityType = Literal["low", "medium", "high"]
OpenAIImageBackgroundType = Literal["transparent", "opaque", "auto"]
OpenAIImageInputFidelityType = Literal["low", "high"]


class OpenAIImgGenFactory:
    LEGACY_ASPECT_RATIO_TO_SIZE: ClassVar[dict[AspectRatio, tuple[OpenAIImageLegacySizeType, int, int]]] = {
        AspectRatio.SQUARE: ("1024x1024", 1024, 1024),
        AspectRatio.LANDSCAPE_3_2: ("1536x1024", 1536, 1024),
        AspectRatio.PORTRAIT_2_3: ("1024x1536", 1024, 1536),
    }
    LEGACY_SIZE_TO_DIMENSIONS: ClassVar[dict[str, tuple[OpenAIImageLegacySizeType, int, int]]] = {
        size: (size, width, height) for size, width, height in LEGACY_ASPECT_RATIO_TO_SIZE.values()
    }

    GPT_IMAGE_2_ASPECT_RATIO_TO_SIZE: ClassVar[dict[AspectRatio, tuple[int, int]]] = {
        AspectRatio.SQUARE: (1024, 1024),
        AspectRatio.LANDSCAPE_4_3: (1536, 1152),
        AspectRatio.LANDSCAPE_3_2: (1536, 1024),
        AspectRatio.LANDSCAPE_16_9: (1536, 864),
        AspectRatio.LANDSCAPE_21_9: (1792, 768),
        AspectRatio.PORTRAIT_3_4: (1152, 1536),
        AspectRatio.PORTRAIT_2_3: (1024, 1536),
        AspectRatio.PORTRAIT_9_16: (864, 1536),
        AspectRatio.PORTRAIT_9_21: (768, 1792),
    }
    GPT_IMAGE_2_EDGE_MULTIPLE: ClassVar[int] = 16
    GPT_IMAGE_2_MAX_EDGE_EXCLUSIVE: ClassVar[int] = 3840
    GPT_IMAGE_2_MAX_LONG_SHORT_RATIO: ClassVar[float] = 3.0
    GPT_IMAGE_2_MIN_PIXELS: ClassVar[int] = 655_360
    GPT_IMAGE_2_MAX_PIXELS: ClassVar[int] = 8_294_400
    GPT_IMAGE_2_RELIABILITY_PIXELS: ClassVar[int] = 2560 * 1440

    @classmethod
    def size_for_legacy_openai_image(
        cls,
        *,
        model_name: str,
        aspect_ratio: AspectRatio,
        size: ImageSize | None,
    ) -> tuple[OpenAIImageLegacySizeType, int, int]:
        if size is not None:
            size_string = cls._size_to_string(size)
            if legacy_size := cls.LEGACY_SIZE_TO_DIMENSIONS.get(size_string):
                return legacy_size
            else:
                supported_sizes = ", ".join(sorted(cls.LEGACY_SIZE_TO_DIMENSIONS))
                msg = f"Size '{size_string}' is not supported by OpenAI image model '{model_name}'. Supported sizes are: {supported_sizes}"
                raise ImgGenParameterError(msg)

        if legacy_size := cls.LEGACY_ASPECT_RATIO_TO_SIZE.get(aspect_ratio):
            return legacy_size

        supported_aspect_ratios = ", ".join(aspect_ratio.value for aspect_ratio in cls.LEGACY_ASPECT_RATIO_TO_SIZE)
        msg = (
            f"Aspect ratio '{aspect_ratio}' is not supported by OpenAI image model '{model_name}'. "
            f"Supported aspect ratios are: {supported_aspect_ratios}"
        )
        raise ImgGenParameterError(msg)

    @classmethod
    def size_for_gpt_image_2(
        cls,
        *,
        model_name: str,
        aspect_ratio: AspectRatio,
        size: ImageSize | None,
    ) -> tuple[str, int, int]:
        if size is None:
            width, height = cls.GPT_IMAGE_2_ASPECT_RATIO_TO_SIZE[aspect_ratio]
            size = ImageSize(width=width, height=height)
        cls.validate_gpt_image_2_size(model_name=model_name, size=size)
        return cls._size_to_string(size), size.width, size.height

    @classmethod
    def validate_gpt_image_2_size(cls, *, model_name: str, size: ImageSize) -> None:
        size_string = cls._size_to_string(size)
        width = size.width
        height = size.height

        if width % cls.GPT_IMAGE_2_EDGE_MULTIPLE != 0 or height % cls.GPT_IMAGE_2_EDGE_MULTIPLE != 0:
            msg = f"Size '{size_string}' is invalid for OpenAI image model '{model_name}': width and height must be multiples of 16"
            raise ImgGenParameterError(msg)

        max_edge = max(width, height)
        if max_edge >= cls.GPT_IMAGE_2_MAX_EDGE_EXCLUSIVE:
            msg = f"Size '{size_string}' is invalid for OpenAI image model '{model_name}': max edge must be less than 3840 pixels"
            raise ImgGenParameterError(msg)

        min_edge = min(width, height)
        long_short_ratio = max_edge / min_edge
        if long_short_ratio > cls.GPT_IMAGE_2_MAX_LONG_SHORT_RATIO:
            msg = f"Size '{size_string}' is invalid for OpenAI image model '{model_name}': long-to-short edge ratio must be at most 3:1"
            raise ImgGenParameterError(msg)

        total_pixels = width * height
        if total_pixels < cls.GPT_IMAGE_2_MIN_PIXELS:
            msg = f"Size '{size_string}' is invalid for OpenAI image model '{model_name}': total pixels must be at least {cls.GPT_IMAGE_2_MIN_PIXELS}"
            raise ImgGenParameterError(msg)
        if total_pixels > cls.GPT_IMAGE_2_MAX_PIXELS:
            msg = f"Size '{size_string}' is invalid for OpenAI image model '{model_name}': total pixels must be at most {cls.GPT_IMAGE_2_MAX_PIXELS}"
            raise ImgGenParameterError(msg)

        if total_pixels > cls.GPT_IMAGE_2_RELIABILITY_PIXELS:
            log.warning(f"Size '{size_string}' is valid for OpenAI image model '{model_name}', but it is above the 2560x1440 reliability boundary.")

    @classmethod
    def output_format_for_openai_image(cls, output_format: ImageFormat | None) -> OpenAIImageOutputFormatType | None:
        if output_format is None:
            return None
        match output_format:
            case ImageFormat.PNG:
                return "png"
            case ImageFormat.JPEG:
                return "jpeg"
            case ImageFormat.WEBP:
                return "webp"

    @classmethod
    def moderation_for_openai_image(cls, is_moderated: bool | None) -> OpenAIImageModerationType:
        if is_moderated is None:
            return omit
        if is_moderated:
            return "low"
        return "auto"

    @classmethod
    def quality_for_openai_image(cls, quality: Quality) -> OpenAIImageQualityType:
        match quality:
            case Quality.LOW:
                return "low"
            case Quality.MEDIUM:
                return "medium"
            case Quality.HIGH:
                return "high"

    @classmethod
    def background_for_openai_image(cls, background: Background) -> OpenAIImageBackgroundType:
        match background:
            case Background.TRANSPARENT:
                return "transparent"
            case Background.OPAQUE:
                return "opaque"
            case Background.AUTO:
                return "auto"

    @classmethod
    def input_fidelity_for_openai_image(cls, input_fidelity: InputFidelity) -> OpenAIImageInputFidelityType:
        match input_fidelity:
            case InputFidelity.LOW:
                return "low"
            case InputFidelity.HIGH:
                return "high"

    @classmethod
    def output_compression_for_openai_image(cls) -> int:
        return 100

    @staticmethod
    def _size_to_string(size: ImageSize) -> str:
        return f"{size.width}x{size.height}"
