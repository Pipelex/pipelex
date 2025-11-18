from pipelex.cogt.exceptions import ImgGenParameterError
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, OutputFormat
from pipelex.types import StrEnum


class AzureSize(StrEnum):
    SQUARE = "1024x1024"
    LANDSCAPE_3_2 = "1536x1024"
    PORTRAIT_2_3 = "1024x1536"


class AzureOutputFormat(StrEnum):
    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"


class AzureImgGenFactory:
    @classmethod
    def image_size_for_azure(cls, aspect_ratio: AspectRatio) -> tuple[AzureSize, int, int]:
        """Convert our aspect ratio to Azure image size format."""
        match aspect_ratio:
            case AspectRatio.SQUARE:
                return AzureSize.SQUARE, 1024, 1024
            case AspectRatio.LANDSCAPE_3_2:
                return AzureSize.LANDSCAPE_3_2, 1536, 1024
            case AspectRatio.PORTRAIT_2_3:
                return AzureSize.PORTRAIT_2_3, 1024, 1536
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
    def output_format_for_azure(cls, output_format: OutputFormat) -> AzureOutputFormat:
        """Convert our output format to Azure format."""
        match output_format:
            case OutputFormat.PNG:
                return AzureOutputFormat.PNG
            case OutputFormat.JPG:
                return AzureOutputFormat.JPEG
            case OutputFormat.WEBP:
                return AzureOutputFormat.WEBP
