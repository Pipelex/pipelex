from typing import Any, Optional

from mistralai import Mistral
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import OcrCapabilityError, SdkTypeError
from pipelex.cogt.ocr.ocr_engine import OcrEngine
from pipelex.cogt.ocr.ocr_input import OcrInputError
from pipelex.cogt.ocr.ocr_job import OcrJob
from pipelex.cogt.ocr.ocr_output import OcrOutput
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract
from pipelex.plugins.mistral.mistral_factory import MistralFactory
from pipelex.plugins.mistral.mistral_utils import upload_file_for_ocr
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.base_64_utils import load_binary_as_base64_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64
from pipelex.tools.misc.path_utils import clarify_path_or_url


class MistralOcrWorker(OcrWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        ocr_engine: OcrEngine,
        reporting_delegate: Optional[ReportingProtocol] = None,
    ):
        super().__init__(ocr_engine=ocr_engine, reporting_delegate=reporting_delegate)

        if not isinstance(sdk_instance, Mistral):
            raise SdkTypeError(f"Provided OCR sdk_instance for {self.__class__.__name__} is not of type Mistral: it's a '{type(sdk_instance)}'")

        self.mistral_client: Mistral = sdk_instance

    @override
    async def _ocr_extract_pages(
        self,
        ocr_job: OcrJob,
    ) -> OcrOutput:
        # TODO: report usage
        if image_uri := ocr_job.ocr_input.image_uri:
            ocr_output = await self.make_ocr_output_from_image(
                image_uri=image_uri,
                should_caption_image=ocr_job.job_params.should_caption_images,
            )

        elif pdf_uri := ocr_job.ocr_input.pdf_uri:
            ocr_output = await self.make_ocr_output_from_pdf(
                pdf_uri=pdf_uri,
                should_include_images=ocr_job.job_params.should_include_images,
                should_caption_images=ocr_job.job_params.should_caption_images,
                should_include_page_views=ocr_job.job_params.should_include_page_views,
            )
        else:
            raise OcrInputError("No image nor PDF URI provided in OcrJob")
        return ocr_output

    async def make_ocr_output_from_image(
        self,
        image_uri: str,
        should_caption_image: bool = False,
    ) -> OcrOutput:
        if should_caption_image:
            raise NotImplementedError("Captioning is not implemented for Mistral OCR.")
        image_path, image_url = clarify_path_or_url(path_or_uri=image_uri)
        if image_url:
            return await self.extract_from_image_url(
                image_url=image_url,
            )
        else:
            assert image_path is not None  # Type narrowing for mypy
            return await self.extract_from_image_file(
                image_path=image_path,
            )

    async def make_ocr_output_from_pdf(
        self,
        pdf_uri: str,
        should_include_images: bool,
        should_caption_images: bool,
        should_include_page_views: bool,
    ) -> OcrOutput:
        if should_caption_images:
            raise OcrCapabilityError("Captioning is not implemented for Mistral OCR.")
        if should_include_page_views:
            log.debug("Page views are not implemented for Mistral OCR.")
            # TODO: use a model capability flag to check possibility before asking for it
            # it it's asked and not available, raise
            # the caller will be responsible to get the page views using other solution if needed
            # raise OcrCapabilityError("Page views are not implemented for Mistral OCR.")
        pdf_path, pdf_url = clarify_path_or_url(path_or_uri=pdf_uri)  # pyright: ignore
        ocr_output: OcrOutput
        if pdf_url:
            ocr_output = await self.extract_from_pdf_url(
                pdf_url=pdf_url,
                should_include_images=should_include_images,
            )
        else:  # pdf_path must be provided based on validation
            assert pdf_path is not None  # Type narrowing for mypy
            ocr_output = await self.extract_from_pdf_file(
                pdf_path=pdf_path,
                should_include_images=should_include_images,
            )
        return ocr_output

    async def extract_from_image_url(
        self,
        image_url: str,
    ) -> OcrOutput:
        ocr_response = await self.mistral_client.ocr.process_async(
            model=self.ocr_engine.ocr_model_name,
            document={
                "type": "image_url",
                "image_url": image_url,
            },
        )
        ocr_output = await MistralFactory.make_ocr_output_from_mistral_response(
            mistral_ocr_response=ocr_response,
        )
        return ocr_output

    async def extract_from_image_file(
        self,
        image_path: str,
    ) -> OcrOutput:
        b64 = await load_binary_as_base64_async(path=image_path)

        file_type = detect_file_type_from_base64(b64=b64)
        mime_type = file_type.mime

        ocr_response = await self.mistral_client.ocr.process_async(
            model=self.ocr_engine.ocr_model_name,
            document={"type": "image_url", "image_url": f"data:{mime_type};base64,{b64.decode('utf-8')}"},
        )
        ocr_output = await MistralFactory.make_ocr_output_from_mistral_response(
            mistral_ocr_response=ocr_response,
        )
        return ocr_output

    async def extract_from_pdf_url(
        self,
        pdf_url: str,
        should_include_images: bool = False,
    ) -> OcrOutput:
        ocr_response = await self.mistral_client.ocr.process_async(
            model=self.ocr_engine.ocr_model_name,
            document={
                "type": "document_url",
                "document_url": pdf_url,
            },
            include_image_base64=should_include_images,
        )

        ocr_output = await MistralFactory.make_ocr_output_from_mistral_response(
            mistral_ocr_response=ocr_response,
            should_include_images=should_include_images,
        )
        return ocr_output

    async def extract_from_pdf_file(
        self,
        pdf_path: str,
        should_include_images: bool = False,
    ) -> OcrOutput:
        # Upload the file
        uploaded_file_id = await upload_file_for_ocr(
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
