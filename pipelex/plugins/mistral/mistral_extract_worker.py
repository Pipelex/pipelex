from typing import Any

from mistralai import Mistral, MistralError
from typing_extensions import override

from pipelex.cogt.exceptions import ExtractCapabilityError, ExtractJobFailureError, InferenceErrorCategory, SdkTypeError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobParams
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.inference.error_classification import (
    MISTRAL_BILLING_URL,
    is_content_policy_violation,
    is_quota_exhaustion_mistral,
)
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.mistral.mistral_factory import MistralFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol


class MistralExtractWorker(ExtractWorkerAbstract):
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

        if not isinstance(sdk_instance, Mistral):
            msg = f"Provided OCR sdk_instance for {self.__class__.__name__} is not of type Mistral: it's a '{type(sdk_instance)}'"
            raise SdkTypeError(msg)

        self.mistral_client: Mistral = sdk_instance

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        # TODO: report usage
        if image_uri := extract_job.extract_input.image_uri:
            extract_output = await self._extract_page_from_image(
                image_uri=image_uri,
            )

        elif document_uri := extract_job.extract_input.document_uri:
            extract_output = await self._extract_pages_from_document(
                document_uri=document_uri,
                extract_job_params=extract_job.job_params,
            )
        else:
            msg = "No image nor document URI provided in ExtractJob"
            raise ExtractInputError(msg)
        return extract_output

    def _classify_mistral_error(self, exc: MistralError) -> ExtractJobFailureError:
        """Classify a Mistral SDK error into a categorized ExtractJobFailureError."""
        error_message = str(exc)
        status_code = exc.status_code

        if is_quota_exhaustion_mistral(error_message, status_code):
            msg = f"Mistral quota exhausted for model '{self.inference_model.desc}': {exc}"
            return ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.CAPACITY,
                user_action=f"Your Mistral account has exceeded its quota — check billing at {MISTRAL_BILLING_URL}",
            )

        if status_code in {401, 403}:
            msg = f"Mistral authentication error for model '{self.inference_model.desc}': {exc}"
            return ExtractJobFailureError(msg, error_category=InferenceErrorCategory.CONFIGURATION)

        if status_code == 404:
            msg = f"Mistral model '{self.inference_model.desc}' not found: {exc}"
            return ExtractJobFailureError(msg, error_category=InferenceErrorCategory.CONFIGURATION)

        if status_code == 429:
            msg = f"Mistral rate limit exceeded for model '{self.inference_model.desc}': {exc}"
            return ExtractJobFailureError(
                msg,
                error_category=InferenceErrorCategory.TRANSIENT,
                user_action="Rate limited by Mistral — the system will retry automatically",
            )

        if status_code == 400:
            if is_content_policy_violation(error_message):
                msg = f"Content rejected by safety filters for model '{self.inference_model.desc}': {exc}"
                return ExtractJobFailureError(
                    msg,
                    error_category=InferenceErrorCategory.CONTENT,
                    user_action="Content was rejected by safety filters — revise the input",
                )
            msg = f"Mistral bad request error for model '{self.inference_model.desc}': {exc}"
            return ExtractJobFailureError(msg, error_category=InferenceErrorCategory.CONTENT)

        if status_code >= 500:
            msg = f"Mistral server error for model '{self.inference_model.desc}': {exc}"
            return ExtractJobFailureError(msg, error_category=InferenceErrorCategory.TRANSIENT)

        msg = f"Mistral API error for model '{self.inference_model.desc}': {exc}"
        return ExtractJobFailureError(msg, error_category=InferenceErrorCategory.TRANSIENT)

    async def _extract_page_from_image(
        self,
        image_uri: str,
    ) -> ExtractOutput:
        document = await MistralFactory.make_mistral_image_url_chunk_from_uri(uri=image_uri)
        try:
            extract_response = await self.mistral_client.ocr.process_async(
                model=self.inference_model.model_id,
                document=document,
            )
        except MistralError as exc:
            raise self._classify_mistral_error(exc) from exc
        return await MistralFactory.make_extract_output_from_mistral_response(
            mistral_extract_response=extract_response,
        )

    async def _extract_pages_from_document(
        self,
        document_uri: str,
        extract_job_params: ExtractJobParams,
    ) -> ExtractOutput:
        if extract_job_params.should_caption_images:
            msg = "Captioning is not implemented for Mistral OCR."
            raise ExtractCapabilityError(msg)

        document = await MistralFactory.make_mistral_document_url_chunk_from_uri(
            mistral_client=self.mistral_client,
            uri=document_uri,
        )

        # max_nb_images: None=unlimited, 0=no images, N=limit to N images
        image_limit: int | None = extract_job_params.max_nb_images
        image_min_size: int | None = extract_job_params.image_min_size if image_limit != 0 else None

        # include_image_base64 specifies return format; image_limit=0 means no images extracted
        include_image_base64 = True
        try:
            extract_response = await self.mistral_client.ocr.process_async(
                model=self.inference_model.model_id,
                document=document,
                include_image_base64=include_image_base64,
                image_limit=image_limit,
                image_min_size=image_min_size,
            )
        except MistralError as exc:
            raise self._classify_mistral_error(exc) from exc

        return await MistralFactory.make_extract_output_from_mistral_response(
            mistral_extract_response=extract_response,
        )
