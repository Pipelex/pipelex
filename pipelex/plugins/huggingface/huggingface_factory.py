from huggingface_hub.inference._providers import PROVIDER_OR_POLICY_T
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
    def make_huggingface_inference_provider(cls, provider_str: str) -> PROVIDER_OR_POLICY_T:
        match provider_str:
            case "black-forest-labs":
                return "black-forest-labs"
            case "cerebras":
                return "cerebras"
            case "clarifai":
                return "clarifai"
            case "cohere":
                return "cohere"
            case "fal-ai":
                return "fal-ai"
            case "featherless-ai":
                return "featherless-ai"
            case "fireworks-ai":
                return "fireworks-ai"
            case "groq":
                return "groq"
            case "hf-inference":
                return "hf-inference"
            case "hyperbolic":
                return "hyperbolic"
            case "nebius":
                return "nebius"
            case "novita":
                return "novita"
            case "nscale":
                return "nscale"
            case "openai":
                return "openai"
            case "publicai":
                return "publicai"
            case "replicate":
                return "replicate"
            case "sambanova":
                return "sambanova"
            case "scaleway":
                return "scaleway"
            case "together":
                return "together"
            case "zai-org":
                return "zai-org"
            case "auto":
                return "auto"
            case _:
                msg = f"Unknown HuggingFace inference provider: {provider_str}"
                raise ValueError(msg)
