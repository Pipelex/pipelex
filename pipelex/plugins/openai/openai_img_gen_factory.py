from typing import ClassVar, Literal

from openai import Omit, omit

from pipelex import log
from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, InputFidelity, SizeTier

OpenAIImageLegacySizeType = Literal["1024x1024", "1536x1024", "1024x1536"]
OpenAIImageModerationType = Literal["low", "auto"] | Omit
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
        size: SizeTier | ImageSize | None,
    ) -> tuple[OpenAIImageLegacySizeType, int, int]:
        if isinstance(size, SizeTier):
            match size:
                case SizeTier.ONE_K:
                    # The fixed legacy grid IS the 1K class: fall through to the aspect-ratio lookup.
                    size = None
                case SizeTier.HALF_K | SizeTier.TWO_K | SizeTier.FOUR_K:
                    msg = f"Size tier '{size}' is not supported by OpenAI image model '{model_name}'; this model only offers the '1k' class"
                    raise ImgGenParameterError(msg)
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
        size: SizeTier | ImageSize | None,
    ) -> tuple[str, int, int]:
        exact_size: ImageSize
        if isinstance(size, SizeTier):
            exact_size = cls._gpt_image_2_size_for_tier(model_name=model_name, aspect_ratio=aspect_ratio, tier=size)
        elif size is None:
            width, height = cls._gpt_image_2_preset_dimensions(model_name=model_name, aspect_ratio=aspect_ratio)
            exact_size = ImageSize(width=width, height=height)
            cls.validate_gpt_image_2_size(model_name=model_name, size=exact_size)
        else:
            exact_size = size
            cls.validate_gpt_image_2_size(model_name=model_name, size=exact_size)
        return cls._size_to_string(exact_size), exact_size.width, exact_size.height

    @classmethod
    def _gpt_image_2_preset_dimensions(cls, *, model_name: str, aspect_ratio: AspectRatio) -> tuple[int, int]:
        dimensions = cls.GPT_IMAGE_2_ASPECT_RATIO_TO_SIZE.get(aspect_ratio)
        if dimensions is None:
            supported_aspect_ratios = ", ".join(supported_ratio.value for supported_ratio in cls.GPT_IMAGE_2_ASPECT_RATIO_TO_SIZE)
            msg = (
                f"Aspect ratio '{aspect_ratio}' is not supported by OpenAI image model '{model_name}'. "
                f"Supported aspect ratios are: {supported_aspect_ratios}"
            )
            raise ImgGenParameterError(msg)
        return dimensions

    @classmethod
    def _gpt_image_2_size_for_tier(cls, *, model_name: str, aspect_ratio: AspectRatio, tier: SizeTier) -> ImageSize:
        """Derive an exact size from a portable tier by scaling the 1K preset per edge.

        The scaled size runs through the same validator as user-supplied exact sizes,
        which is what makes '4k' (over the caps) and '0.5k' (under the pixel floor)
        honest validation errors rather than silent downgrades.
        """
        width, height = cls._gpt_image_2_preset_dimensions(model_name=model_name, aspect_ratio=aspect_ratio)
        scaled_size: ImageSize
        match tier:
            case SizeTier.HALF_K:
                scaled_size = ImageSize(width=width // 2, height=height // 2)
            case SizeTier.ONE_K:
                scaled_size = ImageSize(width=width, height=height)
            case SizeTier.TWO_K:
                scaled_size = ImageSize(width=width * 2, height=height * 2)
            case SizeTier.FOUR_K:
                scaled_size = ImageSize(width=width * 4, height=height * 4)
        try:
            cls.validate_gpt_image_2_size(model_name=model_name, size=scaled_size, is_tier_derived=True)
        except ImgGenParameterError as exc:
            msg = (
                f"Size tier '{tier}' is not satisfiable by OpenAI image model '{model_name}': the derived size "
                f"{scaled_size.width}x{scaled_size.height} is out of the model's range; use '1k'/'2k' or an exact size"
            )
            raise ImgGenParameterError(msg) from exc
        return scaled_size

    @classmethod
    def validate_gpt_image_2_size(cls, *, model_name: str, size: ImageSize, is_tier_derived: bool = False) -> None:
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
            msg = f"Size '{size_string}' is valid for OpenAI image model '{model_name}', but it is above the 2560x1440 reliability boundary."
            if is_tier_derived:
                # A tier is a portable request, not a hand-picked size: note it quietly.
                log.verbose(msg)
            else:
                log.warning(msg)

    @classmethod
    def moderation_for_openai_image(cls, *, is_moderated: bool | None) -> OpenAIImageModerationType:
        """Map the is_moderated flag to OpenAI's moderation parameter: "auto" is standard filtering, "low" is less restrictive."""
        if is_moderated is None:
            return omit
        if is_moderated:
            return "auto"
        return "low"

    @classmethod
    def input_fidelity_for_openai_image(cls, input_fidelity: InputFidelity) -> OpenAIImageInputFidelityType:
        match input_fidelity:
            case InputFidelity.LOW:
                return "low"
            case InputFidelity.HIGH:
                return "high"

    @staticmethod
    def _size_to_string(size: ImageSize) -> str:
        return f"{size.width}x{size.height}"
