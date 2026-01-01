from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import openai
from portkey_ai import (
    createHeaders,  # type: ignore[reportUnknownVariableType]
)
from pydantic import ValidationError
from typing_extensions import override

from pipelex import pretty_print
from pipelex.cogt.extract.bounding_box import BoundingBox
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.plugins.gateway.gateway_constants import GatewayOpenAISdkVariant
from pipelex.plugins.gateway.gateway_exceptions import GatewayExtractResponseError, GatewayFactoryError
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.plugins.gateway.gateway_protocols import GatewayExtractProtocol
from pipelex.plugins.gateway.gateway_schemas import GatewayExtractPageAzure, GatewayExtractPageMistral
from pipelex.plugins.openai.openai_completions_factory import OpenAICompletionsFactory

if TYPE_CHECKING:
    from portkey_ai.api_resources.utils import GenericResponse

    from pipelex.cogt.inference.inference_job_abstract import InferenceJobAbstract
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.plugin_sdk_registry import Plugin


class GatewayCompletionsFactory(OpenAICompletionsFactory):
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
                        extracted_page_image.top_left_x
                        and extracted_page_image.top_left_y
                        and extracted_page_image.bottom_right_x
                        and extracted_page_image.bottom_right_y
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

    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return GatewayFactory.make_extras(inference_model=inference_model, inference_job=inference_job, output_desc=output_desc)
