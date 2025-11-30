from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import openai
from portkey_ai import (
    AsyncPortkey,
    createHeaders,  # type: ignore[reportUnknownVariableType]
)

from pipelex import log
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.plugins.portkey.portkey_exceptions import PortkeyFactoryError
from pipelex.types import StrEnum

if TYPE_CHECKING:
    from portkey_ai.api_resources.utils import GenericResponse

    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
    from pipelex.plugins.plugin_sdk_registry import Plugin


class PortkeyOpenAISdkVariant(StrEnum):
    PORTKEY_COMPLETIONS = "portkey_completions"
    PORTKEY_RESPONSES = "portkey_responses"


class PortkeyFactory:
    @classmethod
    def make_portkey_client(
        cls,
        backend: InferenceBackend,
    ) -> AsyncPortkey:
        log.verbose(f"Making Portkey client with endpoint: {backend.endpoint}")
        is_debug = backend.extra_config.get("debug", False)
        if backend.endpoint is None:
            msg = "Portkey endpoint is not set"
            raise PortkeyFactoryError(msg)

        return AsyncPortkey(
            base_url=backend.endpoint,
            api_key=backend.api_key,
            debug=is_debug,
        )

    @classmethod
    def make_portkey_openai_client(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> openai.AsyncOpenAI:
        log.verbose(f"Making AsyncOpenAI client with endpoint: {backend.endpoint}")
        try:
            sdk_variant = PortkeyOpenAISdkVariant(plugin.sdk)
        except ValueError as exc:
            msg = f"Plugin '{plugin}' is not supported by OpenAIFactory"
            raise PortkeyFactoryError(msg) from exc
        if backend.endpoint is None:
            msg = "Portkey endpoint is not set"
            raise PortkeyFactoryError(msg)

        is_debug = backend.extra_config.get("debug", False)

        the_client: openai.AsyncOpenAI
        match sdk_variant:
            case PortkeyOpenAISdkVariant.PORTKEY_COMPLETIONS:
                the_client = openai.AsyncOpenAI(
                    base_url=backend.endpoint,
                    api_key="",
                    default_headers=createHeaders(
                        api_key=backend.api_key,
                        strict_open_ai_compliance=False,
                        debug=is_debug,
                    ),  # type: ignore[call-overload]
                )
            case PortkeyOpenAISdkVariant.PORTKEY_RESPONSES:
                the_client = openai.AsyncOpenAI(
                    base_url=backend.endpoint,
                    api_key="",
                    default_headers=createHeaders(
                        api_key=backend.api_key,
                        debug=is_debug,
                    ),  # type: ignore[call-overload]
                )
        return the_client

    @classmethod
    def make_extract_output_from_portkey_response(
        cls,
        response: GenericResponse,
    ) -> ExtractOutput:
        if not hasattr(response, "pages"):
            msg = "Portkey extract response does not have pages"
            raise PortkeyFactoryError(msg)
        pages: dict[int, Page] = {}
        for extracted_page in response.pages:  # pyright: ignore[reportUnknownMemberType, reportAttributeAccessIssue, reportUnknownVariableType]
            if not isinstance(extracted_page, dict):
                msg = "Extracted page is not a dictionary"
                raise PortkeyFactoryError(msg)
            extracted_page_dict = cast("dict[str, Any]", extracted_page)
            page_index = extracted_page_dict.get("index")
            if page_index is None:
                msg = "Page index is not set"
                raise PortkeyFactoryError(msg)
            extracted_page_text = extracted_page_dict.get("markdown")
            if extracted_page_text is None:
                msg = "Page text is not set"
                raise PortkeyFactoryError(msg)
            extracted_page_images = extracted_page_dict.get("images")
            if extracted_page_images is None:
                msg = "Page images are not set"
                raise PortkeyFactoryError(msg)
            page_images: list[ExtractedImageFromPage] = []
            for extracted_page_image in extracted_page_images:
                extracted_image = ExtractedImageFromPage(
                    image_id=extracted_page_image["id"],
                    base_64=extracted_page_image["image_base64"],
                    caption=extracted_page_image["image_annotation"],
                )
                page_images.append(extracted_image)
            pages[page_index] = Page(
                text=extracted_page_text,
                extracted_images=page_images,
                page_view=None,
            )
        return ExtractOutput(
            pages=pages,
        )
