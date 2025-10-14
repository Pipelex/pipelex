from typing import Any

from mistralai import Mistral
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ExtractCapabilityError, SdkTypeError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.mistral.mistral_factory import MistralFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.base_64_utils import load_binary_as_base64_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64
from pipelex.tools.misc.path_utils import clarify_path_or_url


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
            extract_output = await self._make_extract_output_from_image(
                image_uri=image_uri,
                should_caption_image=extract_job.job_params.should_caption_images,
            )

        elif pdf_uri := extract_job.extract_input.pdf_uri:
            extract_output = await self._make_extract_output_from_pdf(
                pdf_uri=pdf_uri,
                should_include_images=extract_job.job_params.should_include_images,
                should_caption_images=extract_job.job_params.should_caption_images,
                should_include_page_views=extract_job.job_params.should_include_page_views,
            )
        else:
            msg = "No image nor PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)
        return extract_output

    async def _make_extract_output_from_image(
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

    async def _make_extract_output_from_pdf(
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
            log.debug("Page views are not implemented for Mistral OCR.")
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
        extract_response = await self.mistral_client.ocr.process_async(
            model=self.inference_model.model_id,
            document={
                "type": "image_url",
                "image_url": image_url,
            },
        )
        return await MistralFactory.make_extract_output_from_mistral_response(
            mistral_extract_response=extract_response,
        )

    async def extract_from_image_file(
        self,
        image_path: str,
    ) -> ExtractOutput:
        b64 = await load_binary_as_base64_async(path=image_path)

        file_type = detect_file_type_from_base64(b64=b64)
        mime_type = file_type.mime

        extract_response = await self.mistral_client.ocr.process_async(
            model=self.inference_model.model_id,
            document={"type": "image_url", "image_url": f"data:{mime_type};base64,{b64.decode('utf-8')}"},
        )
        return await MistralFactory.make_extract_output_from_mistral_response(
            mistral_extract_response=extract_response,
        )

    async def extract_from_pdf_url(
        self,
        pdf_url: str,
        should_include_images: bool = False,
    ) -> ExtractOutput:
        extract_response = await self.mistral_client.ocr.process_async(
            model=self.inference_model.model_id,
            document={
                "type": "document_url",
                "document_url": pdf_url,
            },
            include_image_base64=should_include_images,
        )

        return await MistralFactory.make_extract_output_from_mistral_response(
            mistral_extract_response=extract_response,
            should_include_images=should_include_images,
        )

    async def extract_from_pdf_file(
        self,
        pdf_path: str,
        should_include_images: bool = False,
    ) -> ExtractOutput:
        # Upload the file
        uploaded_file_id = await MistralFactory.upload_file_to_mistral_for_ocr(
            mistral_client=self.mistral_client,
            file_path=pdf_path,
        )

        # Get signed URL
        signed_url = await self.mistral_client.files.get_signed_url_async(
            file_id=uploaded_file_id,
        )
        return await self.extract_from_pdf_url(
            pdf_url=signed_url.url,
            should_include_images=should_include_images,
        )
