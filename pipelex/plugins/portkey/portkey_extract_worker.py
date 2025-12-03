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
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.config import get_config
from pipelex.plugins.portkey.portkey_completions_factory import PortkeyCompletionsFactory
from pipelex.plugins.portkey.portkey_constants import PortkeyHeaderKey
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.base_64_utils import make_base_64_url_from_location_async
from pipelex.types import StrEnum


class DocumentType(StrEnum):
    IMAGE = "image"
    PDF = "pdf"

    @property
    def document_tag(self) -> str:
        match self:
            case DocumentType.IMAGE:
                return "image_url"
            case DocumentType.PDF:
                return "document_url"


class PortkeyExtractWorker(ExtractWorkerAbstract):
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
        tenacity_config = get_config().cogt.tenacity_config
        self.retryer = AsyncRetrying(
            retry=retry_if_exception(self._is_retryable_portkey_error),
            before_sleep=self._log_retry,
            wait=wait_random_exponential(
                multiplier=tenacity_config.wait_multiplier,
                max=tenacity_config.wait_max,
                exp_base=tenacity_config.wait_exp_base,
            ),
            reraise=True,
            stop=stop_after_attempt(tenacity_config.max_retries),
        )

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        if image_uri := extract_job.extract_input.image_uri:
            if extract_job.job_params.should_caption_images:
                msg = f"Captioning is not implemented by '{self.inference_model.tag}'."
                raise NotImplementedError(msg)
            base64_url = await make_base_64_url_from_location_async(location=image_uri)
            extract_output = await self.extract_base64_url(
                base64_url=base64_url,
                document_type=DocumentType.IMAGE,
                should_include_images=False,
            )

        elif pdf_uri := extract_job.extract_input.pdf_uri:
            if extract_job.job_params.should_caption_images:
                msg = f"Captioning is not implemented by '{self.inference_model.tag}'."
                raise ExtractCapabilityError(msg)
            if extract_job.job_params.should_include_page_views:
                log.verbose(f"Page views are not implemented by '{self.inference_model.tag}'.")
                # TODO: use a model capability flag to check possibility before asking for it
                # it it's asked and not available, raise
                # the caller will be responsible to get the page views using other solution if needed
            base64_url = await make_base_64_url_from_location_async(location=pdf_uri)
            extract_output = await self.extract_base64_url(
                base64_url=base64_url,
                document_type=DocumentType.PDF,
                should_include_images=extract_job.job_params.should_include_images,
            )
        else:
            msg = "No image nor PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)
        return extract_output

    async def extract_base64_url(
        self,
        base64_url: str,
        document_type: DocumentType,
        should_include_images: bool = False,
    ) -> ExtractOutput:
        config_id = self._get_portkey_config_id()
        log.dev(f"Extracting using config '{config_id}' with should_include_images: {should_include_images}")
        doc_tag = document_type.document_tag

        response: GenericResponse | None = None
        async for attempt in self.retryer:
            with attempt:
                response = await self.portkey_client.with_options(config=config_id).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                    "/",
                    model=self.inference_model.model_id,
                    document={"type": doc_tag, doc_tag: base64_url},
                    include_image_base64=True,
                )

        if response is None:
            msg = f"Could not get a response for model '{self.inference_model.model_id}' via Portkey"
            raise ExtractJobFailureError(msg)

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)
        return PortkeyCompletionsFactory.make_extract_output_from_portkey_response(
            response=response,
        )

    def _get_portkey_config_id(self) -> str:
        if not self.inference_model.extra_headers:
            msg = f"{PortkeyHeaderKey.CONFIG} header is required"
            raise ExtractInputError(msg)
        config_id = self.inference_model.extra_headers.get(PortkeyHeaderKey.CONFIG)
        if not config_id:
            msg = f"{PortkeyHeaderKey.CONFIG} header is required"
            raise ExtractInputError(msg)
        return config_id

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
