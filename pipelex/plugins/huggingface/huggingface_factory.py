import io

from PIL import Image

from pipelex.cogt.exceptions import ImgGenGenerationError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.img_gen.img_gen_job_components import OutputFormat


class HuggingFaceFactory:
    @classmethod
    def make_generated_image(cls, pil_image: Image.Image, output_format: OutputFormat | None) -> GeneratedImageRawDetails:
        """Convert a PIL Image to GeneratedImageRawDetails.

        Args:
            pil_image: The PIL Image returned by HuggingFace's text_to_image
            output_format: The desired output format (PNG, JPEG, or WEBP)

        Returns:
            GeneratedImageRawDetails with the image bytes and metadata
        """
        try:
            width, height = pil_image.size

            # Determine the output format and MIME type
            resolved_format = output_format or OutputFormat.PNG
            mime_type = resolved_format.as_mime_type

            # Convert PIL Image to bytes
            buffer = io.BytesIO()
            pil_format: str
            match resolved_format:
                case OutputFormat.PNG:
                    pil_format = "PNG"
                case OutputFormat.JPEG:
                    pil_format = "JPEG"
                case OutputFormat.WEBP:
                    pil_format = "WEBP"

            pil_image.save(buffer, format=pil_format)
            image_bytes = buffer.getvalue()

            return GeneratedImageRawDetails(
                width=width,
                height=height,
                actual_bytes=image_bytes,
                mime_type=mime_type,
            )
        except (ValueError, OSError, AttributeError) as exc:
            msg = f"Failed to convert HuggingFace PIL image to GeneratedImageRawDetails: {exc}"
            raise ImgGenGenerationError(msg) from exc

    @classmethod
    def make_generated_image_list(
        cls,
        pil_images: list[Image.Image],
        output_format: OutputFormat | None,
    ) -> list[GeneratedImageRawDetails]:
        """Convert a list of PIL Images to GeneratedImageRawDetails list.

        Args:
            pil_images: List of PIL Images returned by HuggingFace
            output_format: The desired output format (PNG, JPEG, or WEBP)

        Returns:
            List of GeneratedImageRawDetails
        """
        return [cls.make_generated_image(pil_image=img, output_format=output_format) for img in pil_images]
