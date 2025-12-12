from typing import Literal

from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, OutputFormat

GatewayImageSizeType = Literal[
    "square",
    "landscape_4_3",
    "landscape_3_2",
    "landscape_16_9",
    "landscape_21_9",
    "portrait_3_4",
    "portrait_2_3",
    "portrait_9_16",
    "portrait_9_21",
]

GatewayOutputFormatType = Literal["png", "jpg", "webp"]
GatewayMimeSubtypeType = Literal["png", "jpeg", "webp"]


class GatewayImgGenFactory:
    @classmethod
    def image_size_for_gateway(cls, aspect_ratio: AspectRatio) -> GatewayImageSizeType:
        # Pipelex AspectRatio values match Gateway expected strings (see sample: "landscape_4_3")
        match aspect_ratio:
            case AspectRatio.SQUARE:
                return "square"
            case AspectRatio.LANDSCAPE_4_3:
                return "landscape_4_3"
            case AspectRatio.LANDSCAPE_3_2:
                return "landscape_3_2"
            case AspectRatio.LANDSCAPE_16_9:
                return "landscape_16_9"
            case AspectRatio.LANDSCAPE_21_9:
                return "landscape_21_9"
            case AspectRatio.PORTRAIT_3_4:
                return "portrait_3_4"
            case AspectRatio.PORTRAIT_2_3:
                return "portrait_2_3"
            case AspectRatio.PORTRAIT_9_16:
                return "portrait_9_16"
            case AspectRatio.PORTRAIT_9_21:
                return "portrait_9_21"

    @classmethod
    def output_format_for_gateway(cls, output_format: OutputFormat) -> GatewayOutputFormatType:
        match output_format:
            case OutputFormat.PNG:
                return "png"
            case OutputFormat.JPG:
                return "jpg"
            case OutputFormat.WEBP:
                return "webp"

    @classmethod
    def mime_subtype_for_output_format(cls, output_format: OutputFormat) -> GatewayMimeSubtypeType:
        # For data URIs / mime types, jpg should use jpeg.
        match output_format:
            case OutputFormat.PNG:
                return "png"
            case OutputFormat.JPG:
                return "jpeg"
            case OutputFormat.WEBP:
                return "webp"
