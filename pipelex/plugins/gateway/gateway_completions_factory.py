from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

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
from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.cogt.document.prompt_document_utils import prep_prompt_documents
from pipelex.cogt.extract.bounding_box import BoundingBox
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.cogt.image.prompt_image import PromptImageDetail
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images
from pipelex.plugins.gateway.gateway_constants import GatewayOpenAISdkVariant
from pipelex.plugins.gateway.gateway_exceptions import GatewayExtractResponseError, GatewayFactoryError
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.plugins.gateway.gateway_protocols import GatewayExtractProtocol
from pipelex.plugins.gateway.gateway_schemas import GatewayExtractPageAzure, GatewayExtractPageDeepseek, GatewayExtractPageMistral
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.tools.uri.prepared_file import PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath

if TYPE_CHECKING:
    from portkey_ai.api_resources.utils import GenericResponse

    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.plugin_sdk_registry import Plugin


class GatewayCompletionsFactory(OpenAICompletionsFactory):
    @override
    async def make_simple_messages(
        self,
        llm_job: LLMJob,
    ) -> list[ChatCompletionMessageParam]:
        """Override to use image_url format for documents which Portkey/Gateway translates correctly."""
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

        # Handle documents using image_url format with data URL - Portkey/Gateway translates this correctly
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
        is_debug_enabled = GatewayFactory.is_debug_enabled(backend=backend)
        endpoint = GatewayFactory.get_endpoint(backend=backend)
        api_key = GatewayFactory.get_api_key(backend=backend)

        if not GatewayOpenAISdkVariant.is_completions(plugin.sdk):
            msg = f"Plugin '{plugin}' is not supported by '{cls.__name__}'"
            raise GatewayFactoryError(msg)

        return openai.AsyncOpenAI(
            base_url=endpoint,
            api_key="",
            default_headers=createHeaders(
                api_key=api_key,
                strict_open_ai_compliance=False,
                debug=is_debug_enabled,
            ),  # type: ignore[call-overload]
        )

    @classmethod
    def make_extract_output_from_response(
        cls,
        inference_model: InferenceModelSpec,
        response: GenericResponse,
    ) -> ExtractOutput:
        extract_protocol = GatewayExtractProtocol.make_from_model_handle(model_handle=inference_model.name)
        match extract_protocol:
            case GatewayExtractProtocol.MISTRAL_DOC_AI:
                return cls._make_extract_output_from_response_mistral(response=response)
            case GatewayExtractProtocol.AZURE_DOC_INTEL:
                return cls._make_extract_output_from_response_azure(response=response)
            case GatewayExtractProtocol.DEEPSEEK_OCR:
                return cls._make_extract_output_from_response_deepseek(response=response)

    @classmethod
    def _make_extract_output_from_response_azure(
        cls,
        response: GenericResponse,
    ) -> ExtractOutput:
        if not hasattr(response, "pages"):
            msg = "Gateway extract response does not have pages"
            raise GatewayExtractResponseError(msg)
        try:
            response_page_dicts = cast("list[dict[str, Any]]", response.pages)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
            pages: dict[int, Page] = {}
            for response_page_dict in response_page_dicts:
                response_page = GatewayExtractPageAzure.model_validate(response_page_dict)
                page_index = response_page.index
                extracted_page_text = response_page.markdown
                extracted_page_images = response_page.images
                page_images: list[ExtractedImageFromPage] = []
                for extracted_page_image in extracted_page_images:
                    extracted_image = ExtractedImageFromPage(
                        size=None,
                        base64_str=extracted_page_image.base64_str,
                        mime_type=extracted_page_image.mime_type,
                        caption=extracted_page_image.caption,
                        bounding_box=extracted_page_image.bounding_box,
                    )
                    page_images.append(extracted_image)
                pages[page_index] = Page(
                    text=extracted_page_text,
                    extracted_images=page_images,
                )
            return ExtractOutput(pages=pages)
        except (TypeError, ValidationError) as exc:
            msg = f"Error parsing Gateway extract response from pages using Azure schema: {exc}"
            raise GatewayExtractResponseError(msg) from exc

    @classmethod
    def _make_extract_output_from_response_mistral(
        cls,
        response: GenericResponse,
    ) -> ExtractOutput:
        if not hasattr(response, "pages"):
            msg = "Gateway extract response does not have pages"
            raise GatewayExtractResponseError(msg)
        try:
            response_page_dicts = cast("list[dict[str, Any]]", response.pages)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
            pages: dict[int, Page] = {}
            for response_page_dict in response_page_dicts:
                response_page = GatewayExtractPageMistral.model_validate(response_page_dict)
                page_index = response_page.index
                extracted_page_text = response_page.markdown
                extracted_page_images = response_page.images
                page_images: list[ExtractedImageFromPage] = []
                for extracted_page_image in extracted_page_images:
                    prefixed_base64 = extracted_page_image.image_base64
                    if not prefixed_base64:
                        continue
                    bounding_box: BoundingBox | None = None
                    if (
                        extracted_page_image.top_left_x is not None
                        and extracted_page_image.top_left_y is not None
                        and extracted_page_image.bottom_right_x is not None
                        and extracted_page_image.bottom_right_y is not None
                    ):
                        bounding_box = BoundingBox.make_from_two_corners(
                            top_left_x=cast("float", extracted_page_image.top_left_x),
                            top_left_y=cast("float", extracted_page_image.top_left_y),
                            bottom_right_x=cast("float", extracted_page_image.bottom_right_x),
                            bottom_right_y=cast("float", extracted_page_image.bottom_right_y),
                        )
                    extracted_image = ExtractedImageFromPage(
                        size=None,
                        actual_url_or_prefixed_base64=prefixed_base64,
                        caption=extracted_page_image.image_annotation,
                        bounding_box=bounding_box,
                    )
                    page_images.append(extracted_image)
                pages[page_index] = Page(
                    text=extracted_page_text,
                    extracted_images=page_images,
                )
            return ExtractOutput(pages=pages)
        except (TypeError, ValidationError) as exc:
            msg = f"Error parsing Gateway extract response from pages using Mistral schema: {exc}"
            raise GatewayExtractResponseError(msg) from exc

    @classmethod
    def _make_extract_output_from_response_deepseek(
        cls,
        response: GenericResponse,
    ) -> ExtractOutput:
        if not hasattr(response, "pages"):
            msg = "Gateway extract response does not have pages"
            raise GatewayExtractResponseError(msg)
        try:
            response_page_dicts = cast("list[dict[str, Any]]", response.pages)  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue]
            pages: dict[int, Page] = {}
            for response_page_dict in response_page_dicts:
                response_page = GatewayExtractPageDeepseek.model_validate(response_page_dict)
                page_index = response_page.index
                if response_page.source_image_info and response_page.source_image_info.scaled_down:
                    original = response_page.source_image_info.original
                    processed = response_page.source_image_info.processed
                    log.warning(
                        f"Extract page [{page_index}]: image was scaled down from {original.width}x{original.height} "
                        f"({original.bytes / 1024:.1f} KB) to {processed.width}x{processed.height} ({processed.bytes / 1024:.1f} KB)"
                    )
                extracted_page_text = response_page.markdown
                pages[page_index] = Page(
                    text=extracted_page_text,
                    extracted_images=[],
                )
            return ExtractOutput(pages=pages)
        except (TypeError, ValidationError) as exc:
            msg = f"Error parsing Gateway extract response from pages using Deepseek schema: {exc}"
            raise GatewayExtractResponseError(msg) from exc

    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return GatewayFactory.make_extras(inference_model=inference_model, inference_job=inference_job, output_desc=output_desc)
