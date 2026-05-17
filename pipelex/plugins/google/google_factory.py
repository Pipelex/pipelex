import asyncio
import base64

from google.genai import types as genai_types
from google.genai.client import Client as GoogleGenAiClient

from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.document.prompt_document_utils import prepare_prompt_document_as_base64
from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.image.prompt_image_utils import prepare_prompt_image_as_base64
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.config import get_config


class GoogleFactory:
    @classmethod
    def make_google_client(cls, backend: InferenceBackend) -> GoogleGenAiClient:
        """Create a Google Gemini API client."""
        # Tier 1 transport retry: the Google GenAI SDK does NOT retry transient transport failures
        # unless retry_options is set. Wire it explicitly from config so it matches the other
        # SDK-backed workers. HttpRetryOptions.attempts counts the original attempt, hence the +1.
        transport_max_retries = get_config().cogt.transport_max_retries
        http_options = genai_types.HttpOptions(retry_options=genai_types.HttpRetryOptions(attempts=transport_max_retries + 1))
        return GoogleGenAiClient(api_key=backend.api_key, http_options=http_options)

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
    def extract_text_from_response(cls, response: genai_types.GenerateContentResponse, model_desc: str) -> str:
        """Extract text from a Google Gemini response, skipping thinking parts.

        Args:
            response: The Google Gemini API response.
            model_desc: Model description for error messages.

        Returns:
            The concatenated text content from non-thinking parts.

        """
        if not response.candidates:
            msg = f"No candidates returned from model: {model_desc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Google Gemini returned no candidates — try rephrasing the prompt or using a different model",
                ),
            )

        candidate = response.candidates[0]
        if not candidate.content or not candidate.content.parts:
            msg = f"No content parts in response from model: {model_desc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Google Gemini returned a candidate with no content parts — try rephrasing the prompt or using a different model",
                ),
            )

        text_parts: list[str] = []
        for part in candidate.content.parts:
            if part.thought:
                continue
            if part.text:
                stripped = part.text.strip()
                if stripped:
                    text_parts.append(stripped)

        if not text_parts:
            msg = f"No text content in response from model: {model_desc}"
            raise LLMCompletionError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                provider_metadata=None,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="Google Gemini returned only thinking parts and no text — shorten the prompt, raise max_tokens, or disable thinking",
                ),
            )

        return "\n\n".join(text_parts)

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

        # Add thinking/reasoning tokens if available
        if usage_metadata.thoughts_token_count:
            nb_tokens_by_category[TokenCategory.OUTPUT_REASONING] = usage_metadata.thoughts_token_count

        return nb_tokens_by_category
