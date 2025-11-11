import openai
from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_content_part_image_param import ImageURL
from openai.types.completion_usage import CompletionUsage

from pipelex import log
from pipelex.cogt.exceptions import LLMPromptParameterError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBase64, PromptImagePath, PromptImageUrl
from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.model_backends.backend import InferenceBackend
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.plugins.groq.groq_exceptions import GroqFactoryError
from pipelex.plugins.plugin_sdk_registry import Plugin
from pipelex.tools.misc.base_64_utils import load_binary_as_base64
from pipelex.types import StrEnum


class GroqSdkVariant(StrEnum):
    GROQ = "groq"


class GroqFactory:
    @classmethod
    def make_groq_client(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> openai.AsyncOpenAI:
        """Create AsyncOpenAI client configured for Groq API endpoint."""
        try:
            sdk_variant = GroqSdkVariant(plugin.sdk)
        except ValueError as exc:
            msg = f"Plugin '{plugin}' is not supported by GroqFactory"
            raise GroqFactoryError(msg) from exc

        # Groq API key handling (similar to OpenAI - empty string works for local models)
        api_key = backend.api_key or ""

        # Groq's OpenAI-compatible endpoint
        groq_base_url = backend.endpoint if backend.endpoint else "https://api.groq.com/openai/v1"

        match sdk_variant:
            case GroqSdkVariant.GROQ:
                log.verbose(f"Making AsyncOpenAI client for Groq with endpoint: {groq_base_url}")
                the_client = openai.AsyncOpenAI(
                    api_key=api_key,
                    base_url=groq_base_url,
                    timeout=60.0,  # Default 1 minute
                    max_retries=2,
                )

        return the_client

    @classmethod
    def make_simple_messages(
        cls,
        llm_job: LLMJob,
    ) -> list[ChatCompletionMessageParam]:
        """Makes a list of messages with a system message (if provided) and followed by a user message."""
        llm_prompt = llm_job.llm_prompt
        messages: list[ChatCompletionMessageParam] = []
        user_contents: list[ChatCompletionContentPartParam] = []

        if system_content := llm_prompt.system_text:
            messages.append(ChatCompletionSystemMessageParam(role="system", content=system_content))

        if user_prompt_text := llm_prompt.user_text:
            user_part_text = ChatCompletionContentPartTextParam(text=user_prompt_text, type="text")
            user_contents.append(user_part_text)

        if llm_prompt.user_images:
            for prompt_image in llm_prompt.user_images:
                groq_image_url = cls.make_groq_image_url(prompt_image=prompt_image)
                image_param = ChatCompletionContentPartImageParam(image_url=groq_image_url, type="image_url")
                user_contents.append(image_param)

        messages.append(ChatCompletionUserMessageParam(role="user", content=user_contents))
        return messages

    @classmethod
    def make_groq_image_url(cls, prompt_image: PromptImage) -> ImageURL:
        """Convert PromptImage to Groq-compatible ImageURL format.

        Groq supports:
        - Direct URLs (max 20MB)
        - Base64 data URIs (max 4MB)
        - Max resolution: 33 megapixels
        - Max 5 images per request
        """
        if isinstance(prompt_image, PromptImageUrl):
            url = prompt_image.url
            groq_image_url = ImageURL(url=url, detail="high")
        elif isinstance(prompt_image, PromptImageBase64):
            # Detect media type from base64 if possible, default to jpeg
            media_type = cls._detect_image_media_type(prompt_image.base_64) or "jpeg"
            url_with_bytes: str = f"data:image/{media_type};base64,{prompt_image.base_64.decode('utf-8')}"
            groq_image_url = ImageURL(url=url_with_bytes, detail="high")
        elif isinstance(prompt_image, PromptImagePath):
            image_bytes = load_binary_as_base64(path=prompt_image.file_path)
            return cls.make_groq_image_url(PromptImageBase64(base_64=image_bytes))
        else:
            msg = f"prompt_image of type {type(prompt_image)} is not supported"
            raise LLMPromptParameterError(msg)
        return groq_image_url

    @staticmethod
    def _detect_image_media_type(base64_bytes: bytes) -> str | None:
        """Detect image media type from base64 bytes header."""
        try:
            # Check first few bytes for common image signatures
            if base64_bytes.startswith(b"\xff\xd8\xff"):
                return "jpeg"
            elif base64_bytes.startswith(b"\x89PNG"):
                return "png"
            elif base64_bytes.startswith(b"GIF"):
                return "gif"
            elif base64_bytes.startswith(b"RIFF") and b"WEBP" in base64_bytes[:12]:
                return "webp"
        except Exception as e:
            log.warning(e)
        return "jpeg"  # Default to jpeg

    @staticmethod
    def make_openai_error_info(exception: Exception) -> str:
        """Map OpenAI exceptions to user-friendly error messages for Groq."""
        error_mapping: dict[type, str] = {
            openai.BadRequestError: "Groq API request was invalid.",
            openai.InternalServerError: "Groq is having trouble. Please try again later.",
            openai.RateLimitError: "Groq API request exceeded rate limit.",
            openai.AuthenticationError: "Groq API request was not authorized.",
            openai.PermissionDeniedError: "Groq API request was not permitted.",
            openai.NotFoundError: "Requested resource not found.",
            openai.APITimeoutError: "Groq API request timed out.",
            openai.APIConnectionError: "Groq API request failed to connect.",
            openai.APIError: "Groq API returned an API Error.",
        }
        return error_mapping.get(type(exception), "An unexpected error occurred with the Groq API.")

    @staticmethod
    def make_nb_tokens_by_category(usage: CompletionUsage) -> NbTokensByCategoryDict:
        """Extract token usage from OpenAI-compatible response."""
        nb_tokens_by_category: NbTokensByCategoryDict = {
            TokenCategory.INPUT: usage.prompt_tokens,
            TokenCategory.OUTPUT: usage.completion_tokens,
        }

        # Groq may support cached tokens in the future
        if prompt_tokens_details := usage.prompt_tokens_details:
            if hasattr(prompt_tokens_details, "cached_tokens") and prompt_tokens_details.cached_tokens:
                nb_tokens_by_category[TokenCategory.INPUT_CACHED] = prompt_tokens_details.cached_tokens

        return nb_tokens_by_category
