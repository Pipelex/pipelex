import asyncio
import base64

from google import genai
from google.genai import types as genai_types

from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.document.prompt_document_utils import prepare_prompt_document_as_base64
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.image.prompt_image_utils import prepare_prompt_image_as_base64
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory


class GoogleFactory:
    @classmethod
    def make_google_client(cls, backend: InferenceBackend) -> genai.Client:
        """Create a Google Gemini API client."""
        return genai.Client(api_key=backend.api_key)

    @classmethod
    async def prepare_image_part(cls, prompt_image: PromptImage) -> genai_types.Part:
        """Convert a PromptImage to Google genai Part format.

        Uses the unified prepare_prompt_image_as_base64() which supports all URI types
        including pipelex-storage://.
        """
        prepared = await prepare_prompt_image_as_base64(prompt_image)
        image_bytes = base64.b64decode(prepared.base64_data)
        return genai_types.Part.from_bytes(data=image_bytes, mime_type=prepared.mime_type)

    @classmethod
    async def prepare_document_part(cls, prompt_document: PromptDocument) -> genai_types.Part:
        """Convert a PromptDocument to Google genai Part format.

        Uses the unified prepare_prompt_document_as_base64() which supports all URI types
        including pipelex-storage://.
        """
        prepared = await prepare_prompt_document_as_base64(prompt_document)
        document_bytes = base64.b64decode(prepared.base64_data)
        return genai_types.Part.from_bytes(data=document_bytes, mime_type=prepared.mime_type)

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

        # Add document parts if present
        if llm_prompt.user_documents:
            # Prepare all documents in parallel
            document_tasks = [cls.prepare_document_part(document) for document in llm_prompt.user_documents]
            document_parts = await asyncio.gather(*document_tasks)
            parts.extend(document_parts)

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
