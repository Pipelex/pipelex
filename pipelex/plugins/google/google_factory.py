import asyncio
from typing import Any, List, Optional, Type, Union

import instructor
from google import genai
from google.genai import types
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import CogtError, LLMCompletionError
from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBytes,
    PromptImagePath,
    PromptImageUrl,
)
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_worker_internal_abstract import LLMWorkerInternalAbstract
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.base_64_utils import load_binary_as_base64_async
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar


class GoogleFactoryError(CogtError):
    pass


class GoogleFactory:
    @staticmethod
    def make_google_client(backend: InferenceBackend) -> genai.Client:
        """Create a Google Gemini API client."""
        return genai.Client(api_key=backend.api_key)

    @classmethod
    async def prepare_image_part(cls, prompt_image: PromptImage) -> types.Part:
        """Convert a PromptImage to Google genai Part format."""
        image_bytes: bytes
        mime_type: str

        if isinstance(prompt_image, PromptImageBytes):
            # Decode base64 to bytes
            import base64

            image_bytes = base64.b64decode(prompt_image.base_64)
            file_type = prompt_image.get_file_type()
            # Use the mime type from FileType object
            mime_type = file_type.mime
        elif isinstance(prompt_image, PromptImagePath):
            # Load image from path as base64 and decode
            import base64

            base64_bytes = await load_binary_as_base64_async(prompt_image.file_path)
            image_bytes = base64.b64decode(base64_bytes)
            file_type = prompt_image.get_file_type()
            # Use the mime type from FileType object
            mime_type = file_type.mime
        elif isinstance(prompt_image, PromptImageUrl):
            # Download image from URL
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(prompt_image.url) as response:
                    image_bytes = await response.read()
            # Detect mime type from bytes
            from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes

            file_type = detect_file_type_from_bytes(image_bytes)
            # Use the mime type from FileType object
            mime_type = file_type.mime
        else:
            raise GoogleFactoryError(f"Unsupported PromptImage type: '{type(prompt_image).__name__}'")

        # Create Google Part from bytes
        return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    @classmethod
    async def prepare_contents(cls, llm_prompt: LLMPrompt) -> Any:  # Returns ContentListUnion compatible type
        """Prepare contents for Google genai API."""
        # If only text, return as string
        if llm_prompt.user_text and not llm_prompt.user_images:
            return llm_prompt.user_text

        # Build list of parts for multimodal content
        parts: List[Union[str, types.Part]] = []

        # Add text content if present
        if llm_prompt.user_text:
            parts.append(llm_prompt.user_text)

        # Add image parts if present
        if llm_prompt.user_images:
            # Prepare all images in parallel
            image_tasks = [cls.prepare_image_part(image) for image in llm_prompt.user_images]
            image_parts = await asyncio.gather(*image_tasks)
            parts.extend(image_parts)

        # Return the parts list, which is compatible with generate_content
        return parts

    @classmethod
    def extract_token_usage(cls, usage_metadata: Optional[types.GenerateContentResponseUsageMetadata]) -> NbTokensByCategoryDict:
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
