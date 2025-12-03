from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import openai
from portkey_ai import (
    createHeaders,  # type: ignore[reportUnknownVariableType]
)
from typing_extensions import override

from pipelex import log
from pipelex.cogt.extract.extract_output import ExtractedImageFromPage, ExtractOutput, Page
from pipelex.hub import get_telemetry_manager
from pipelex.plugins.openai.openai_responses_factory import OpenAIResponsesFactory
from pipelex.plugins.portkey.portkey_constants import PortkeyHeaderKey, PortkeyOpenAISdkVariant
from pipelex.plugins.portkey.portkey_exceptions import PortkeyFactoryError
from pipelex.plugins.portkey.portkey_factory import PortkeyFactory

if TYPE_CHECKING:
    from portkey_ai.api_resources.utils import GenericResponse

    from pipelex.cogt.llm.llm_job import LLMJob
    from pipelex.cogt.model_backends.backend import InferenceBackend
    from pipelex.plugins.plugin_sdk_registry import Plugin


class PortkeyResponsesFactory(OpenAIResponsesFactory):
    @classmethod
    def make_portkey_openai_client_for_responses(
        cls,
        plugin: Plugin,
        backend: InferenceBackend,
    ) -> openai.AsyncOpenAI:
        is_debug_enabled = PortkeyFactory.is_debug_enabled(backend=backend)
        endpoint = PortkeyFactory.get_endpoint(backend=backend)
        api_key = PortkeyFactory.get_api_key(backend=backend)
        log.verbose(f"Making AsyncOpenAI client with endpoint: {endpoint}, debug: {is_debug_enabled}")
        if not PortkeyOpenAISdkVariant.is_responses(plugin.sdk):
            msg = f"Plugin '{plugin}' is not supported by '{cls.__name__}'"
            raise PortkeyFactoryError(msg)

        return openai.AsyncOpenAI(
            base_url=endpoint,
            api_key="",
            default_headers=createHeaders(
                api_key=api_key,
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

    @override
    def make_extra_headers(self, llm_job: LLMJob, output_desc: str) -> dict[str, str]:
        if not get_telemetry_manager().is_portkey_tracing_enabled():
            return {}
        if llm_job.job_metadata.pipe_job_ids:
            last_pipe_job_id = llm_job.job_metadata.pipe_job_ids[-1]
        else:
            last_pipe_job_id = "main"
        extra_headers: dict[str, str] = {}
        extra_headers[PortkeyHeaderKey.TRACE_ID] = llm_job.job_metadata.pipeline_run_id
        if not llm_job.job_metadata.unit_job_id:
            msg = f"Unit job id is not set for LLM job: {llm_job}"
            raise PortkeyFactoryError(msg)
        model_kind = llm_job.job_metadata.unit_job_id.model_kind
        span_id = f"{model_kind} -> {output_desc}"
        extra_headers[PortkeyHeaderKey.SPAN_ID] = span_id
        extra_headers[PortkeyHeaderKey.SPAN_NAME] = f"{last_pipe_job_id}: {span_id}"
        return extra_headers
