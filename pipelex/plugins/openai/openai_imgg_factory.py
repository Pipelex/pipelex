from typing import Literal

from pipelex.cogt.exceptions import ImggParameterError
from pipelex.cogt.imgg.imgg_job_components import AspectRatio, Background, OutputFormat, Quality

GptImage1SizeType = Literal["1024x1024", "1536x1024", "1024x1536"]
GptImage1OutputFormatType = Literal["png", "jpeg", "webp"]
GptImage1ModerationType = Literal["low", "auto"]
GptImage1QualityType = Literal["low", "medium", "high"]
GptImage1BackgroundType = Literal["transparent", "opaque", "auto"]


class OpenAIImggFactory:
    @classmethod
    def image_size_for_gpt_image_1(cls, aspect_ratio: AspectRatio) -> GptImage1SizeType:
        match aspect_ratio:
            case AspectRatio.SQUARE:
                return "1024x1024"
            case AspectRatio.LANDSCAPE_3_2:
                return "1536x1024"
            case AspectRatio.PORTRAIT_2_3:
                return "1024x1536"
            case (
                AspectRatio.LANDSCAPE_4_3
                | AspectRatio.LANDSCAPE_16_9
                | AspectRatio.LANDSCAPE_21_9
                | AspectRatio.PORTRAIT_3_4
                | AspectRatio.PORTRAIT_9_16
                | AspectRatio.PORTRAIT_9_21
            ):
                raise ImggParameterError(f"Aspect ratio '{aspect_ratio}' is not supported by GPT Image 1 model")

    @classmethod
    def output_format_for_gpt_image_1(cls, output_format: OutputFormat) -> GptImage1OutputFormatType:
        match output_format:
            case OutputFormat.PNG:
                return "png"
            case OutputFormat.JPG:
                return "jpeg"
            case OutputFormat.WEBP:
                return "webp"

    @classmethod
    def moderation_for_gpt_image_1(cls, is_moderated: bool) -> GptImage1ModerationType:
        return "auto" if is_moderated else "low"

    @classmethod
    def quality_for_gpt_image_1(cls, quality: Quality) -> GptImage1QualityType:
        """This method only converts the Quality string value as a Literal, as expected by the OpenAI API"""
        return quality.value

    @classmethod
    def background_for_gpt_image_1(cls, background: Background) -> GptImage1BackgroundType:
        """This method only converts the Background string value as a Literal, as expected by the OpenAI API"""
        return background.value
