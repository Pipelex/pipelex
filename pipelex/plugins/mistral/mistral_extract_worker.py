from typing import Any

from mistralai import Mistral
from typing_extensions import override

from pipelex.cogt.exceptions import ExtractCapabilityError, SdkTypeError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_job_components import ExtractJobParams
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
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

    async def _extract_page_from_image(
        self,
        image_uri: str,
    ) -> ExtractOutput:
        document = await MistralFactory.make_mistral_image_url_chunk_from_uri(uri=image_uri)
        extract_response = await self.mistral_client.ocr.process_async(
            model=self.inference_model.model_id,
            document=document,
        )
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
        extract_response = await self.mistral_client.ocr.process_async(
            model=self.inference_model.model_id,
            document=document,
            include_image_base64=include_image_base64,
            image_limit=image_limit,
            image_min_size=image_min_size,
        )

        return await MistralFactory.make_extract_output_from_mistral_response(
            mistral_extract_response=extract_response,
        )
