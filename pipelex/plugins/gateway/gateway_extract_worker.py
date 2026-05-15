import asyncio
from typing import Any

from portkey_ai import AsyncPortkey
from portkey_ai.api_resources import exceptions as portkey_exceptions
from portkey_ai.api_resources.utils import GenericResponse
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_random_exponential
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ExtractCapabilityError, ExtractJobFailureError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind, extract_gateway_metadata
from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.usage.token_category import TokenCategory
from pipelex.config import get_config
from pipelex.hub import get_storage_provider
from pipelex.plugins.gateway.gateway_completions_factory import GatewayCompletionsFactory
from pipelex.plugins.gateway.gateway_deck import GatewayDeck
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.plugins.gateway.gateway_protocols import GatewayExtractProtocol
from pipelex.plugins.gateway.gateway_search_schemas import GatewayFetchRequestParams
from pipelex.reporting.reporting_protocol import ReportingProtocol
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
        self._tenacity_config = get_config().cogt.tenacity_config

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
                    except Exception as exc:
                        log.debug(f"Error closing portkey httpx client during teardown: {exc}")
        except Exception as exc:
            log.debug(f"Error during GatewayExtractWorker teardown: {exc}")

    def _make_retryer(self) -> AsyncRetrying:
        """Create a fresh AsyncRetrying instance for each extraction call.

        This is necessary because AsyncRetrying is stateful and cannot be shared
        across parallel async calls without causing race conditions.
        """
        return AsyncRetrying(
            retry=retry_if_exception(self._is_retryable_portkey_error),
            before_sleep=self._log_retry,
            wait=wait_random_exponential(
                multiplier=self._tenacity_config.wait_multiplier,
                max=self._tenacity_config.wait_max,
                exp_base=self._tenacity_config.wait_exp_base,
            ),
            reraise=True,
            stop=stop_after_attempt(self._tenacity_config.max_retries),
        )

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

        attempt_number = 0
        response: GenericResponse | None = None
        retryer = self._make_retryer()
        try:
            async for attempt in retryer:
                with attempt:
                    attempt_number += 1
                    response = await self.portkey_client.with_options(config=config_id).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                        "/chat/completions",
                        model=self.inference_model.model_id,
                        messages=messages,
                    )
        except portkey_exceptions.APIError as exc:
            error_summary = GatewayFactory.make_error_summary_from_portkey_error(exc)
            error_category = GatewayFactory.classify_error_category(exc)
            user_action = GatewayFactory.make_user_action_from_portkey_error(exc)
            metadata = extract_gateway_metadata(exc)
            msg = (
                f"Web fetch service error for URL '{document_uri}' via model '{self.inference_model.tag}' "
                f"after {attempt_number} attempt(s): {error_summary}"
            )
            raise ExtractJobFailureError(
                msg,
                error_category=error_category,
                user_action=user_action,
                provider_metadata=metadata,
            ) from exc

        if response is None:
            msg = f"Could not get a response for model '{self.inference_model.tag}' via Portkey after {attempt_number} attempts"
            raise ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CONTACT_SUPPORT,
                    detail="The Gateway returned no response — retry, and report this if it persists",
                ),
                provider_metadata=None,
            )

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
        base64_url: str,
        should_include_images: bool = False,
    ) -> ExtractOutput:
        config_id = GatewayDeck.get_config_id(headers=self.inference_model.extra_headers or {})
        log.dev(f"Extracting using config '{config_id}' with should_include_images: {should_include_images}")

        attempt_number = 0
        response: GenericResponse | None = None
        retryer = self._make_retryer()
        try:
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
            async for attempt in retryer:
                with attempt:
                    attempt_number += 1
                    response = await self.portkey_client.with_options(config=config_id).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                        "/chat/completions",
                        model=self.inference_model.model_id,
                        headers=extra_headers,
                        **extra_body,
                    )
        except portkey_exceptions.APIError as exc:
            error_summary = GatewayFactory.make_error_summary_from_portkey_error(exc)
            error_category = GatewayFactory.classify_error_category(exc)
            user_action = GatewayFactory.make_user_action_from_portkey_error(exc)
            metadata = extract_gateway_metadata(exc)
            msg = f"Extract service error for model '{self.inference_model.tag}' after {attempt_number} attempt(s): {error_summary}"
            raise ExtractJobFailureError(
                msg,
                error_category=error_category,
                user_action=user_action,
                provider_metadata=metadata,
            ) from exc

        if response is None:
            msg = f"Could not get a response for model '{self.inference_model.tag}' via Portkey after {attempt_number} attempts"
            raise ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.UNKNOWN,
                user_action=UserAction(
                    kind=UserActionKind.CONTACT_SUPPORT,
                    detail="The Gateway returned no response — retry, and report this if it persists",
                ),
                provider_metadata=None,
            )

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)

        return GatewayCompletionsFactory.make_extract_output_from_response(inference_model=self.inference_model, response=response)

    def _is_retryable_portkey_error(self, exc: BaseException) -> bool:
        if isinstance(exc, portkey_exceptions.NotFoundError):
            msg = str(exc).lower()
            return "specified deployment could not be found" in msg
        # Transient upstream gateway failures (e.g. openrouter 500s during batch fetches)
        # should be retried rather than killing the whole batch on the first hiccup.
        return isinstance(exc, (portkey_exceptions.InternalServerError, portkey_exceptions.APITimeoutError, portkey_exceptions.APIConnectionError))

    def _log_retry(self, retry_state: RetryCallState) -> None:
        """Called before sleeping between retries."""
        if not retry_state.outcome:
            log.error("Tenacity retry state outcome is None")
            return
        exc = retry_state.outcome.exception()
        attempt = retry_state.attempt_number
        wait_duration = retry_state.next_action.sleep if retry_state.next_action else 0.0
        log.dev(f"{self.__class__.__name__} retry #{attempt} for '{self.inference_model.model_id}' due to '{type(exc).__name__}' (service is flaky).")
        log.verbose(f"Wait duration before next attempt: {wait_duration:.4f}s")
