import base64
from typing import Any

from portkey_ai import AsyncPortkey
from portkey_ai.api_resources import exceptions as portkey_exceptions
from portkey_ai.api_resources.utils import GenericResponse
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, stop_after_attempt, wait_fixed
from typing_extensions import override

from pipelex import log, pretty_print
from pipelex.cogt.exceptions import ExtractCapabilityError, ExtractJobFailureError, SdkTypeError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.portkey.portkey_factory import PortkeyFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.path_utils import clarify_path_or_url


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

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        if image_uri := extract_job.extract_input.image_uri:
            extract_output = await self._extract_from_image(
                image_uri=image_uri,
                should_caption_image=extract_job.job_params.should_caption_images,
            )

        elif pdf_uri := extract_job.extract_input.pdf_uri:
            extract_output = await self._extract_from_pdf(
                pdf_uri=pdf_uri,
                should_include_images=extract_job.job_params.should_include_images,
                should_caption_images=extract_job.job_params.should_caption_images,
                should_include_page_views=extract_job.job_params.should_include_page_views,
            )
        else:
            msg = "No image nor PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)
        return extract_output

    async def _extract_from_image(
        self,
        image_uri: str,
        should_caption_image: bool = False,
    ) -> ExtractOutput:
        if should_caption_image:
            msg = "Captioning is not implemented for Mistral OCR."
            raise NotImplementedError(msg)
        image_path, image_url = clarify_path_or_url(path_or_uri=image_uri)
        if image_url:
            return await self.extract_from_image_url(
                image_url=image_url,
            )
        assert image_path is not None
        return await self.extract_from_image_file(
            image_path=image_path,
        )

    async def _extract_from_pdf(
        self,
        pdf_uri: str,
        should_include_images: bool,
        should_caption_images: bool,
        should_include_page_views: bool,
    ) -> ExtractOutput:
        if should_caption_images:
            msg = "Captioning is not implemented for Mistral OCR."
            raise ExtractCapabilityError(msg)
        if should_include_page_views:
            log.verbose("Page views are not implemented for Mistral OCR.")
            # TODO: use a model capability flag to check possibility before asking for it
            # it it's asked and not available, raise
            # the caller will be responsible to get the page views using other solution if needed
            # raise OcrCapabilityError("Page views are not implemented for Mistral OCR.")
        pdf_path, pdf_url = clarify_path_or_url(path_or_uri=pdf_uri)
        extract_output: ExtractOutput
        if pdf_url:
            extract_output = await self.extract_from_pdf_url(
                pdf_url=pdf_url,
                should_include_images=should_include_images,
            )
        else:  # pdf_path must be provided based on validation
            assert pdf_path is not None
            extract_output = await self.extract_from_pdf_file(
                pdf_path=pdf_path,
                should_include_images=should_include_images,
            )
        return extract_output

    async def extract_from_image_url(
        self,
        image_url: str,
    ) -> ExtractOutput:
        # extract_response = await self.portkey_client.ocr.process_async(
        #     model=self.inference_model.model_id,
        #     document={
        #         "type": "image_url",
        #         "image_url": image_url,
        #     },
        # )
        # return await PortkeyFactory.make_extract_output_from_mistral_response(
        #     mistral_extract_response=extract_response,
        # )
        msg = "Not implemented for Portkey"
        raise NotImplementedError(msg)

    async def extract_from_image_file(
        self,
        image_path: str,
    ) -> ExtractOutput:
        # b64 = await load_binary_as_base64_async(path=image_path)

        # file_type = detect_file_type_from_base64(b64=b64)
        # mime_type = file_type.mime

        # extract_response = await self.portkey_client.ocr.process_async(
        #     model=self.inference_model.model_id,
        #     document={"type": "image_url", "image_url": f"data:{mime_type};base64,{b64.decode('utf-8')}"},
        # )
        # return await PortkeyFactory.make_extract_output_from_portkey_response(
        #     mistral_extract_response=extract_response,
        # )
        msg = "Not implemented for Portkey"
        raise NotImplementedError(msg)

    async def extract_from_pdf_url(
        self,
        pdf_url: str,
        should_include_images: bool = False,
    ) -> ExtractOutput:
        # extract_response = await self.portkey_client.ocr.process_async(
        #     model=self.inference_model.model_id,
        #     document={
        #         "type": "document_url",
        #         "document_url": pdf_url,
        #     },
        #     include_image_base64=should_include_images,
        # )

        # return await PortkeyFactory.make_extract_output_from_mistral_response(
        #     mistral_extract_response=extract_response,
        #     should_include_images=should_include_images,
        # )
        msg = "Not implemented for Portkey"
        raise NotImplementedError(msg)

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
        log.dev(f"{self.__class__.__name__} retry #{attempt} for '{self.inference_model.model_id}' due to '{type(exc).__name__}' (service is flaky).")

    async def extract_from_pdf_file(
        self,
        pdf_path: str,
        should_include_images: bool = False,
    ) -> ExtractOutput:
        if not self.inference_model.extra_headers:
            msg = "x-portkey-config header is required"
            raise ExtractInputError(msg)
        config = self.inference_model.extra_headers.get("x-portkey-config")
        if not config:
            msg = "x-portkey-config header is required"
            raise ExtractInputError(msg)
        log.dev(f"Extracting from PDF file: {pdf_path} using config '{config}' with should_include_images: {should_include_images}")

        # Get the base64 string from the PDF
        with open(pdf_path, "rb") as pdf_file:
            base64_pdf = base64.b64encode(pdf_file.read()).decode("utf-8")
        doc_url = f"data:application/pdf;base64,{base64_pdf}"

        retryer = AsyncRetrying(
            retry=retry_if_exception(self._is_retryable_portkey_error),
            before_sleep=self._log_retry,
            wait=wait_fixed(wait=0.02),
            reraise=True,
            stop=stop_after_attempt(50),
        )

        response: GenericResponse | None = None
        async for attempt in retryer:
            with attempt:
                response = await self.portkey_client.with_options(config=config).post(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                    "/",
                    model=self.inference_model.model_id,
                    document={"type": "document_url", "document_url": doc_url},
                    include_image_base64=True,
                )

        if response is None:
            msg = f"Could not get a response for model '{self.inference_model.model_id}' via Portkey"
            raise ExtractJobFailureError(msg)

        if not isinstance(response, GenericResponse):
            msg = "Response is not of type GenericResponse"
            raise TypeError(msg)
        pretty_print(response, title="Portkey response")
        response_dict = response.model_dump()
        pretty_print(response_dict, title="Portkey response dict")
        return PortkeyFactory.make_extract_output_from_portkey_response(
            response=response,
        )
