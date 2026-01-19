from __future__ import annotations

from typing import TYPE_CHECKING, Any

import openai
from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_content_part_image_param import ImageURL as OpenAIImageURL
from portkey_ai import (
    createHeaders,  # type: ignore[reportUnknownVariableType]
)
from typing_extensions import override

from pipelex.cogt.document.prompt_document_utils import prep_prompt_documents
from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.plugins.portkey.portkey_constants import PortkeyOpenAISdkVariant
from pipelex.plugins.portkey.portkey_exceptions import PortkeyFactoryError
from pipelex.plugins.portkey.portkey_factory import PortkeyFactory
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath

if TYPE_CHECKING:
    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.plugin_sdk_registry import Plugin


class PortkeyCompletionsFactory(OpenAICompletionsFactory):
    @override
    async def make_simple_messages(
        self,
        llm_job: LLMJob,
    ) -> list[ChatCompletionMessageParam]:
        """Override to use image_url format for documents which Portkey translates correctly."""
        llm_prompt = llm_job.llm_prompt
        messages: list[ChatCompletionMessageParam] = []
        user_contents: list[ChatCompletionContentPartParam] = []
        if system_content := llm_prompt.system_text:
            messages.append(ChatCompletionSystemMessageParam(role="system", content=system_content))
        if user_prompt_text := llm_prompt.user_text:
            user_part_text = ChatCompletionContentPartTextParam(text=user_prompt_text, type="text")
            user_contents.append(user_part_text)
        if llm_prompt.user_images:
            detail = llm_job.job_params.image_detail or PromptImageDetail.AUTO
            prepped_images = await prep_prompt_images(prompt_images=llm_prompt.user_images, is_http_url_enabled=self.is_http_url_enabled)
            for prepped_image in prepped_images:
                url: str
                match prepped_image:
                    case PreparedFileHttpUrl():
                        url = prepped_image.url
                    case PreparedFileBase64():
                        url = prepped_image.as_data_url()
                    case PreparedFileLocalPath():
                        msg = "PreparedFileLocalPath is not supported for images - should be converted to base64"
                        raise TypeError(msg)

                image_url_obj = OpenAIImageURL(url=url, detail=detail.as_openai_detail)
                image_param = ChatCompletionContentPartImageParam(image_url=image_url_obj, type="image_url")
                user_contents.append(image_param)

        # Handle documents using image_url format with data URL - Portkey translates this to provider-specific format
        # Documents must always be base64 encoded for the image_url format
        if llm_prompt.user_documents:
            prepped_documents = await prep_prompt_documents(prompt_documents=llm_prompt.user_documents, is_http_url_enabled=False)
            for prepped_document in prepped_documents:
                match prepped_document:
                    case PreparedFileBase64():
                        # Use image_url format with data URL - Portkey translates this to provider-specific format
                        doc_url = prepped_document.as_data_url()
                        image_url_obj = OpenAIImageURL(url=doc_url, detail="auto")
                        doc_param = ChatCompletionContentPartImageParam(image_url=image_url_obj, type="image_url")
                        user_contents.append(doc_param)
                    case PreparedFileHttpUrl() | PreparedFileLocalPath():
                        msg = f"{type(prepped_document).__name__} is not supported for documents - should be converted to base64"
                        raise TypeError(msg)

        messages.append(ChatCompletionUserMessageParam(role="user", content=user_contents))
        return messages

    @classmethod
    def make_portkey_openai_client_for_completions(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> openai.AsyncOpenAI:
        is_debug_enabled = PortkeyFactory.is_debug_enabled(backend=backend)
        endpoint = PortkeyFactory.get_endpoint(backend=backend)
        api_key = PortkeyFactory.get_api_key(backend=backend)

        if not PortkeyOpenAISdkVariant.is_completions(plugin.sdk):
            msg = f"Plugin '{plugin}' is not supported by '{cls.__name__}'"
            raise PortkeyFactoryError(msg)

        return openai.AsyncOpenAI(
            base_url=endpoint,
            api_key="",
            default_headers=createHeaders(
                api_key=api_key,
                strict_open_ai_compliance=False,
                debug=is_debug_enabled,
            ),  # type: ignore[call-overload]
        )

    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return PortkeyFactory.make_extras(inference_model=inference_model, inference_job=inference_job, output_desc=output_desc)
