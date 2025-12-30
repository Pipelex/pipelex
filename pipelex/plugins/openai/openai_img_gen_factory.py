from typing import Literal

from openai import Omit, omit

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, Quality
from pipelex.tools.misc.image_utils import ImageFormat

GptImage1SizeType = Literal["1024x1024", "1536x1024", "1024x1536"]
GptImage1OutputFormatType = Literal["png", "jpeg", "webp"]
GptImage1ModerationType = Literal["low", "auto"] | Omit
GptImage1QualityType = Literal["low", "medium", "high"]
GptImage1BackgroundType = Literal["transparent", "opaque", "auto"]


class OpenAIImgGenFactory:
    @classmethod
    def image_size_for_gpt_image_1(cls, aspect_ratio: AspectRatio) -> tuple[GptImage1SizeType, int, int]:
        match aspect_ratio:
            case AspectRatio.SQUARE:
                return "1024x1024", 1024, 1024
            case AspectRatio.LANDSCAPE_3_2:
                return "1536x1024", 1536, 1024
            case AspectRatio.PORTRAIT_2_3:
                return "1024x1536", 1024, 1536
            case (
                AspectRatio.LANDSCAPE_4_3
                | AspectRatio.LANDSCAPE_16_9
                | AspectRatio.LANDSCAPE_21_9
                | AspectRatio.PORTRAIT_3_4
                | AspectRatio.PORTRAIT_9_16
                | AspectRatio.PORTRAIT_9_21
            ):
                msg = f"Aspect ratio '{aspect_ratio}' is not supported by GPT Image 1 model"
                raise ImgGenParameterError(msg)

    @classmethod
    def output_format_for_gpt_image_1(cls, output_format: ImageFormat | None) -> GptImage1OutputFormatType | None:
        """This method only converts the OutputFormat StrEnum value to a Literal, as expected by the OpenAI API"""
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
    def moderation_for_gpt_image_1(cls, is_moderated: bool | None) -> GptImage1ModerationType:
        if is_moderated is None:
            return omit
        elif is_moderated:
            return "low"
        else:
            return "auto"

    @classmethod
    def quality_for_gpt_image_1(cls, quality: Quality) -> GptImage1QualityType:
        """This method only converts the Quality string value as a Literal, as expected by the OpenAI API"""
        return quality.value

    @classmethod
    def background_for_gpt_image_1(cls, background: Background) -> GptImage1BackgroundType:
        """This method only converts the Background string value as a Literal, as expected by the OpenAI API"""
        return background.value

    @classmethod
    def output_compression_for_gpt_image_1(cls) -> int:
        """This method only converts the OutputCompression int value as a Literal, as expected by the OpenAI API"""
        return 100
