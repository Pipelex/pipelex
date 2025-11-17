from typing import Literal

from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, OutputFormat, Quality

AzureSizeType = Literal["1024x1024", "1536x1024", "1024x1536"]
AzureOutputFormatType = Literal["png", "jpeg", "webp"]
AzureQualityType = Literal["low", "medium", "high"]


class AzureImgGenFactory:
    """Factory for converting Pipelex parameters to Azure OpenAI Image API format."""

    @classmethod
    def image_size_for_azure(cls, aspect_ratio: AspectRatio) -> AzureSizeType:
        """Convert Pipelex aspect ratio to Azure image size format."""
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
                msg = f"Aspect ratio '{aspect_ratio}' is not supported by Azure GPT Image model"
                raise ImgGenParameterError(msg)

    @classmethod
    def output_format_for_azure(cls, output_format: OutputFormat) -> AzureOutputFormatType:
        """Convert Pipelex output format to Azure format."""
        match output_format:
            case OutputFormat.PNG:
                return "png"
            case OutputFormat.JPG:
                return "jpeg"
            case OutputFormat.WEBP:
                return "webp"

    @classmethod
    def quality_for_azure(cls, quality: Quality | None) -> AzureQualityType:
        """Convert Pipelex quality to Azure quality format."""
        if quality is None:
            return "medium"
        return quality.value

    @classmethod
    def parse_image_dimensions(cls, size: str) -> tuple[int, int]:
        """Parse Azure size string to width and height."""
        width_str, height_str = size.split("x")
        return int(width_str), int(height_str)
