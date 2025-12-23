from PIL import Image

from pipelex.cogt.exceptions import ImgGenGenerationError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.tools.misc.image_utils import ImageFormat, pil_image_to_bytes


class HuggingFaceFactory:
    @classmethod
    def make_generated_image(cls, pil_image: Image.Image, output_format: ImageFormat | None) -> GeneratedImageRawDetails:
        """Convert a PIL Image to GeneratedImageRawDetails.

        Args:
            pil_image: The PIL Image returned by HuggingFace's text_to_image
            output_format: The desired output format (PNG, JPEG, or WEBP)

        Returns:
            GeneratedImageRawDetails with the image bytes and metadata
        """
        try:
            width, height = pil_image.size
            actual_bytes = pil_image_to_bytes(pil_image=pil_image, image_format=output_format)
            return GeneratedImageRawDetails(
                width=width,
                height=height,
                actual_bytes=actual_bytes,
                output_format=output_format,
            )
        except (ValueError, OSError, AttributeError) as exc:
            msg = f"Failed to convert HuggingFace PIL image to GeneratedImageRawDetails: {exc}"
            raise ImgGenGenerationError(msg) from exc

    @classmethod
    def make_generated_image_list(
        cls,
        pil_images: list[Image.Image],
        output_format: ImageFormat | None,
    ) -> list[GeneratedImageRawDetails]:
        """Convert a list of PIL Images to GeneratedImageRawDetails list.

        Args:
            pil_images: List of PIL Images returned by HuggingFace
            output_format: The desired output format (PNG, JPEG, or WEBP)

        Returns:
            List of GeneratedImageRawDetails
        """
        return [cls.make_generated_image(pil_image=img, output_format=output_format) for img in pil_images]
