import asyncio
from typing import Any

from portkey_ai import AsyncPortkey
from portkey_ai.api_resources import exceptions as portkey_exceptions
from portkey_ai.api_resources.utils import GenericResponse
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ExtractCapabilityError, SdkTypeError
from pipelex.cogt.extract.exceptions import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.inference.error_classification import extract_gateway_metadata
from pipelex.cogt.inference.error_classify import classify_inference_error
from pipelex.cogt.inference.error_render import InferenceErrorFamily, render_inference_error
from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.plugins.gateway.gateway_completions_factory import GatewayCompletionsFactory
from pipelex.plugins.gateway.gateway_deck import GatewayDeck
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.plugins.gateway.gateway_protocols import GatewayExtractProtocol
from pipelex.plugins.gateway.gateway_search_schemas import GatewayFetchRequestParams
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.service_hub import get_storage_provider
from pipelex.tools.uri.uri_resolver import make_base64_url_from_any_uri


class GatewayExtractWorker(ExtractWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(
            extra_config=extra_config,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )

        if not isinstance(sdk_instance, AsyncPortkey):
            msg = f"Provided extraction sdk_instance for {self.__class__.__name__} is not of type Portkey: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.portkey_client: AsyncPortkey = sdk_instance

    @override
    def teardown(self):
        """Close the portkey client's underlying httpx connection pool.

        The httpx client holds TCP connections bound to a specific event loop.
        If the worker is reused across event loop boundaries (e.g. between test
        modules with different class-scoped loops), stale connections cause
        'Event loop is closed' errors. Closing prevents this.
        """
        try:
            httpx_client = getattr(self.portkey_client, "_client", None)
            if httpx_client is not None and hasattr(httpx_client, "is_closed") and not httpx_client.is_closed:
                try:
                    loop = asyncio.get_running_loop()
                    task = loop.create_task(httpx_client.aclose())
                    task.add_done_callback(
                        lambda task_result: log.debug(f"Portkey httpx client cleanup error: {task_result.exception()}")
                        if not task_result.cancelled() and task_result.exception()
                        else None
                    )
                except RuntimeError:
                    # No running event loop, best-effort sync close
                    try:
                        asyncio.run(httpx_client.aclose())
                    except Exception as exc:  # noqa: BLE001
                        # Best-effort: asyncio.run() runs aclose(), whose failure surface is not enumerable; teardown must never fail.
                        log.debug(f"Error closing portkey httpx client during teardown: {exc}")
        except Exception as exc:  # noqa: BLE001
            # Best-effort cleanup boundary: teardown must never fail, whatever client/event-loop close throws.
            log.debug(f"Error during GatewayExtractWorker teardown: {exc}")

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        extract_protocol = GatewayExtractProtocol.make_from_model_handle(model_handle=self.inference_model.name)
        match extract_protocol:
            case GatewayExtractProtocol.LINKUP_FETCH:
                return await self._extract_web_fetch(extract_job=extract_job)
            case GatewayExtractProtocol.MISTRAL_DOC_AI | GatewayExtractProtocol.AZURE_DOC_INTEL | GatewayExtractProtocol.DEEPSEEK_OCR:
                return await self._extract_document(extract_job=extract_job)

    async def _extract_document(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        # max_nb_images: None=unlimited, 0=no images, N=limit to N images
        max_nb_images = extract_job.job_params.max_nb_images
        should_include_images = max_nb_images is None or max_nb_images > 0

        storage = get_storage_provider()

        if image_uri := extract_job.extract_input.image_uri:
            base64_url = await make_base64_url_from_any_uri(uri=image_uri, storage_provider=storage)
            # Images (as input) don't have embedded images to extract
            extract_output = await self._extract_base64_url(
                extract_job=extract_job,
                base64_url=base64_url,
                should_include_images=False,
            )

        elif document_uri := extract_job.extract_input.document_uri:
            if extract_job.job_params.should_caption_images and not self.inference_model.is_caption_supported_for_extract:
                msg = f"Captioning is not supported by '{self.inference_model.tag}'."
                raise ExtractCapabilityError(msg)
            base64_url = await make_base64_url_from_any_uri(uri=document_uri, storage_provider=storage)
            extract_output = await self._extract_base64_url(
                extract_job=extract_job,
                base64_url=base64_url,
                should_include_images=should_include_images,
            )
        else:
            msg = "No image nor document URI provided in ExtractJob"
            raise ExtractInputError(msg)
        return extract_output

    async def _extract_web_fetch(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        """Extract content from a web page via the gateway's linkup-fetch endpoint."""
        document_uri = extract_job.extract_input.document_uri
        if not document_uri:
            msg = "GatewayExtractWorker (linkup-fetch) requires a document_uri (web URL) in ExtractInput"
            raise ExtractInputError(msg)

        job_params = extract_job.job_params
        max_nb_images = job_params.max_nb_images
        extract_images = max_nb_images is None or max_nb_images > 0

        fetch_params = GatewayFetchRequestParams(
            url=document_uri,
            render_js=job_params.render_js,
            include_raw_html=job_params.include_raw_html,
            extract_images=extract_images,
        )

        config_id = GatewayDeck.get_config_id(headers=self.inference_model.extra_headers or {})
        log.dev(f"Web fetch via gateway config '{config_id}' for URL: {document_uri}")

        messages: list[dict[str, str]] = [{"role": "user", "content": fetch_params.model_dump_json()}]

        try:
            response = await self.portkey_client.with_options(config=config_id).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                "/chat/completions",
                model=self.inference_model.model_id,
                messages=messages,
            )
        except portkey_exceptions.APIError as sdk_exc:
            metadata = extract_gateway_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.EXTRACT,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)

        extract_output = GatewayCompletionsFactory.make_extract_output_from_response(inference_model=self.inference_model, response=response)

        # Apply image limit (factory just parses, worker applies limits)
        if max_nb_images is not None and extract_output.pages:
            for page in extract_output.pages.values():
                page.extracted_images = page.extracted_images[:max_nb_images]

        # Per-request cost model: costs are defined per million, so 1 request = 1_000_000
        if extract_tokens_usage := extract_job.job_report.extract_tokens_usage:
            extract_tokens_usage.nb_tokens_by_category = {
                TokenCategory.INPUT: 1_000_000,
                TokenCategory.OUTPUT: 1_000_000,
            }

        return extract_output

    async def _extract_base64_url(
        self,
        extract_job: ExtractJob,
        *,
        base64_url: str,
        should_include_images: bool = False,
    ) -> ExtractOutput:
        config_id = GatewayDeck.get_config_id(headers=self.inference_model.extra_headers or {})
        log.dev(f"Extracting using config '{config_id}' with should_include_images: {should_include_images}")

        extra_headers, extra_body = GatewayFactory.make_extras(
            inference_model=self.inference_model, inference_job=extract_job, output_desc=InferenceOutputType.PAGES
        )
        # Encode document/image as an image_url content part inside messages.
        # Portkey forwards messages but strips custom top-level fields like document/image.
        if extra_body.get("messages"):
            first_msg = extra_body["messages"][0]
            text_content = first_msg["content"]
            first_msg["content"] = [
                {"type": "text", "text": text_content},
                {"type": "image_url", "image_url": {"url": base64_url}},
            ]
        try:
            response = await self.portkey_client.with_options(config=config_id).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                "/chat/completions",
                model=self.inference_model.model_id,
                headers=extra_headers,
                **extra_body,
            )
        except portkey_exceptions.APIError as sdk_exc:
            metadata = extract_gateway_metadata(sdk_exc)
            classification = classify_inference_error(metadata)
            raise render_inference_error(
                metadata=metadata,
                classification=classification,
                family=InferenceErrorFamily.EXTRACT,
                model_desc=self.inference_model.desc,
                model_handle=self.inference_model.name,
            ) from sdk_exc

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)

        return GatewayCompletionsFactory.make_extract_output_from_response(inference_model=self.inference_model, response=response)
