from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import openai
from portkey_ai import (
    createHeaders,  # type: ignore[reportUnknownVariableType]
)
from typing_extensions import override

from pipelex import pretty_print
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.plugins.gateway.gateway_constants import GatewayOpenAISdkVariant
from pipelex.plugins.gateway.gateway_exceptions import GatewayFactoryError
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
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
    def make_extract_output_from_portkey_response(
        cls,
        response: GenericResponse,
    ) -> ExtractOutput:
        if not hasattr(response, "pages"):
            msg = "Portkey extract response does not have pages"
            raise GatewayFactoryError(msg)
        pages: dict[int, Page] = {}
        for extracted_page in response.pages:  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownVariableType]
            if not isinstance(extracted_page, dict):
                msg = "Extracted page is not a dictionary"
                raise GatewayFactoryError(msg)
            extracted_page_dict = cast("dict[str, Any]", extracted_page)
            page_index = extracted_page_dict.get("index")
            if page_index is None:
                msg = "Page index is not set"
                raise GatewayFactoryError(msg)
            extracted_page_text = extracted_page_dict.get("markdown")
            if extracted_page_text is None:
                msg = "Page text is not set"
                raise GatewayFactoryError(msg)
            extracted_page_images = extracted_page_dict.get("images")
            if extracted_page_images is None:
                msg = "Page images are not set"
                raise GatewayFactoryError(msg)
            pretty_print(extracted_page_images, title="Extracted page images")
            page_images: list[ExtractedImageFromPage] = []
            for extracted_page_image in extracted_page_images:
                if not isinstance(extracted_page_image, dict):
                    msg = "Extracted page image is not a dictionary"
                    raise GatewayFactoryError(msg)
                extracted_page_image_dict = cast("dict[str, Any]", extracted_page_image)
                base_64 = extracted_page_image_dict.get("image_base64")
                if base_64 is None:
                    msg = "Got no base 64 for extracted page image"
                    raise GatewayFactoryError(msg)
                # image_id = extracted_page_image_dict.get("id")
                caption = extracted_page_image_dict.get("image_annotation")
                extracted_image = ExtractedImageFromPage(
                    # image_id=image_id,
                    base_64=base_64,
                    caption=caption,
                )
                page_images.append(extracted_image)
            pages[page_index] = Page(
                text=extracted_page_text,
                extracted_images=page_images,
            )
        return ExtractOutput(
            pages=pages,
        )

    @override
    def make_extras(
        self, inference_model: InferenceModelSpec, inference_job: InferenceJobAbstract, output_desc: str
    ) -> tuple[dict[str, str], dict[str, Any]]:
        return GatewayFactory.make_extras(inference_model=inference_model, inference_job=inference_job, output_desc=output_desc)
