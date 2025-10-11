import asyncio

from google import genai
from google.genai import types as genai_types

from pipelex.cogt.exceptions import CogtError
from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBase64,
    PromptImagePath,
    PromptImageUrl,
)
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.tools.misc.base_64_utils import load_binary_async


class GoogleFactoryError(CogtError):
    pass


class GoogleFactory:
    @staticmethod
    def make_google_client(backend: InferenceBackend) -> genai.Client:
        """Create a Google Gemini API client."""
        return genai.Client(api_key=backend.api_key)

    @classmethod
    async def prepare_image_part(cls, prompt_image: PromptImage) -> genai_types.Part:
        """Convert a PromptImage to Google genai Part format."""
        image_bytes: bytes
        mime_type: str

        if isinstance(prompt_image, PromptImageBase64):
            image_bytes = prompt_image.get_decoded_bytes()
            mime_type = prompt_image.get_mime_type()
            return genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        if isinstance(prompt_image, PromptImagePath):
            image_bytes = await load_binary_async(prompt_image.file_path)
            mime_type = prompt_image.get_mime_type()
            return genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        if isinstance(prompt_image, PromptImageUrl):
            prompt_image_binary = await PromptImageFactory.make_promptimagebinary_from_url_async(prompt_image)
            image_bytes = prompt_image_binary.binary
            mime_type = prompt_image_binary.get_mime_type()
            return genai_types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        msg = f"Unsupported PromptImage type: '{type(prompt_image).__name__}'"
        raise GoogleFactoryError(msg)

    @classmethod
    async def prepare_user_contents(cls, llm_prompt: LLMPrompt) -> genai_types.ContentListUnion:
        """Prepare contents for Google genai API."""
        # Build list of parts for multimodal content
        parts: list[genai_types.Part] = []

        # Add text content if present
        if llm_prompt.user_text:
            parts.append(genai_types.Part.from_text(text=llm_prompt.user_text))

        # Add image parts if present
        if llm_prompt.user_images:
            # Prepare all images in parallel
            image_tasks = [cls.prepare_image_part(image) for image in llm_prompt.user_images]
            image_parts = await asyncio.gather(*image_tasks)
            parts.extend(image_parts)

        return genai_types.Content(parts=parts, role="user")

    @classmethod
    def extract_token_usage(cls, usage_metadata: genai_types.GenerateContentResponseUsageMetadata | None) -> NbTokensByCategoryDict:
        """Extract token usage from Google's usage metadata."""
        if not usage_metadata:
            return {}

        nb_tokens_by_category: NbTokensByCategoryDict = {}

        # Add input tokens
        if usage_metadata.prompt_token_count:
            nb_tokens_by_category[TokenCategory.INPUT] = usage_metadata.prompt_token_count

        # Add output tokens
        if usage_metadata.candidates_token_count:
            nb_tokens_by_category[TokenCategory.OUTPUT] = usage_metadata.candidates_token_count

        # Add cached tokens if available
        if usage_metadata.cached_content_token_count:
            nb_tokens_by_category[TokenCategory.INPUT_CACHED] = usage_metadata.cached_content_token_count

        return nb_tokens_by_category
