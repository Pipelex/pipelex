from typing import Any

from portkey_ai import AsyncPortkey
from portkey_ai.api_resources import exceptions as portkey_exceptions
from portkey_ai.api_resources.utils import GenericResponse
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_random_exponential
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ExtractCapabilityError, ExtractJobFailureError, SdkTypeError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.inference.inference_constants import InferenceOutputType
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.plugins.gateway.gateway_completions_factory import GatewayCompletionsFactory
from pipelex.plugins.gateway.gateway_deck import GatewayDeck
from pipelex.plugins.gateway.gateway_factory import GatewayFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.uri.uri_resolver import make_base64_url_from_any_uri
from pipelex.types import StrEnum


class DocumentKind(StrEnum):
    IMAGE = "image"
    DOCUMENT = "document"

    @property
    def document_tag(self) -> str:
        match self:
            case DocumentKind.IMAGE:
                return "image_url"
            case DocumentKind.DOCUMENT:
                return "document_url"


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
        # max_nb_images: None=unlimited, 0=no images, N=limit to N images
        max_nb_images = extract_job.job_params.max_nb_images
        should_include_images = max_nb_images is None or max_nb_images > 0

        if image_uri := extract_job.extract_input.image_uri:
            if extract_job.job_params.should_caption_images:
                msg = f"Captioning is not implemented by '{self.inference_model.tag}'."
                raise NotImplementedError(msg)
            base64_url = await make_base64_url_from_any_uri(uri=image_uri)
            # Images (as input) don't have embedded images to extract
            extract_output = await self._extract_base64_url(
                extract_job=extract_job,
                base64_url=base64_url,
                document_type=DocumentKind.IMAGE,
                should_include_images=False,
            )

        elif document_uri := extract_job.extract_input.document_uri:
            if extract_job.job_params.should_caption_images:
                # TODO: handle model capability and skip UT when it's not supported
                msg = f"Captioning is not implemented by '{self.inference_model.tag}'."
                raise ExtractCapabilityError(msg)
            base64_url = await make_base64_url_from_any_uri(uri=document_uri)
            extract_output = await self._extract_base64_url(
                extract_job=extract_job,
                base64_url=base64_url,
                document_type=DocumentKind.DOCUMENT,
                should_include_images=should_include_images,
            )
        else:
            msg = "No image nor document URI provided in ExtractJob"
            raise ExtractInputError(msg)
        return extract_output

    async def _extract_base64_url(
        self,
        extract_job: ExtractJob,
        base64_url: str,
        document_type: DocumentKind,
        should_include_images: bool = False,
    ) -> ExtractOutput:
        config_id = GatewayDeck.get_config_id(headers=self.inference_model.extra_headers or {})
        log.dev(f"Extracting using config '{config_id}' with should_include_images: {should_include_images}")

        doc_tag = document_type.document_tag
        attempt_number = 0
        response: GenericResponse | None = None
        retryer = self._make_retryer()
        try:
            extra_headers, extra_body = GatewayFactory.make_extras(
                inference_model=self.inference_model, inference_job=extract_job, output_desc=InferenceOutputType.PAGES
            )
            async for attempt in retryer:
                with attempt:
                    attempt_number += 1
                    response = await self.portkey_client.with_options(config=config_id).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                        "/",
                        model=self.inference_model.model_id,
                        document={"type": doc_tag, doc_tag: base64_url},
                        headers=extra_headers,
                        **extra_body,
                    )
        except portkey_exceptions.APIError as exc:
            error_summary = GatewayFactory.make_error_summary_from_portkey_error(exc)
            msg = f"Extract service error for model '{self.inference_model.tag}' after {attempt_number} attempt(s): {error_summary}"
            raise ExtractJobFailureError(msg) from exc

        if response is None:
            msg = f"Could not get a response for model '{self.inference_model.tag}' via Portkey after {attempt_number} attempts"
            raise ExtractJobFailureError(msg)

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)

        return GatewayCompletionsFactory.make_extract_output_from_response(inference_model=self.inference_model, response=response)

    def _is_retryable_portkey_error(self, exc: BaseException) -> bool:
        if isinstance(exc, portkey_exceptions.NotFoundError):
            msg = str(exc).lower()
            return "specified deployment could not be found" in msg
        return False

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
