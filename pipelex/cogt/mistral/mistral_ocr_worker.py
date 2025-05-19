# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, List, Optional

import shortuuid
from mistralai import Mistral
from typing_extensions import override

from pipelex.cogt.exceptions import SdkTypeError
from pipelex.cogt.inference.inference_report_delegate import InferenceReportDelegate
from pipelex.cogt.mistral.mistral_factory import MistralFactory
from pipelex.cogt.mistral.mistral_utils import upload_file_for_ocr
from pipelex.cogt.ocr.ocr_engine import OcrEngine
from pipelex.cogt.ocr.ocr_input import OcrInputError
from pipelex.cogt.ocr.ocr_job import OcrJob
from pipelex.cogt.ocr.ocr_output import OcrExtractedImage, OcrOutput
from pipelex.cogt.ocr.ocr_worker_abstract import OcrWorkerAbstract, ocr_job_func
from pipelex.tools.misc.base_64 import load_binary_as_base64_async
from pipelex.tools.pdf.pdf_render import render_pdf_pages_to_images
from pipelex.tools.utils.path_utils import clarify_path_or_url, ensure_path


class MistralOcrWorker(OcrWorkerAbstract):
    def __init__(
        self,
        sdk_instance: Any,
        ocr_engine: OcrEngine,
        report_delegate: Optional[InferenceReportDelegate] = None,
    ):
        super().__init__(ocr_engine=ocr_engine, report_delegate=report_delegate)

        if not isinstance(sdk_instance, Mistral):
            raise SdkTypeError(f"Provided OCR sdk_instance for {self.__class__.__name__} is not of type Mistral: it's a '{type(sdk_instance)}'")

        self.mistral_client: Mistral = sdk_instance

    @override
    @ocr_job_func
    async def ocr_extract_pages(
        self,
        ocr_job: OcrJob,
    ) -> OcrOutput:
        # TODO: report usage
        if image_uri := ocr_job.ocr_input.image_uri:
            return await self.make_ocr_output_from_image(
                image_uri=image_uri,
                should_caption_image=ocr_job.job_params.should_caption_images,
            )
        elif pdf_uri := ocr_job.ocr_input.pdf_uri:
            return await self.make_ocr_output_from_pdf(
                pdf_uri=pdf_uri,
                should_caption_images=ocr_job.job_params.should_caption_images,
                should_add_screenshots=ocr_job.job_params.should_add_screenshots,
            )
        else:
            raise OcrInputError("No image or PDF URI provided in OcrJob")

    async def make_ocr_output_from_image(
        self,
        image_uri: str,
        should_caption_image: bool = False,
    ) -> OcrOutput:
        if should_caption_image:
            raise NotImplementedError("Captioning is not implemented for Mistral OCR.")
        image_path, image_url = clarify_path_or_url(path_or_url=image_uri)
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
        should_caption_images: bool,
        should_add_screenshots: bool,
    ) -> OcrOutput:
        if should_caption_images:
            raise NotImplementedError("Captioning is not implemented for Mistral OCR.")
        pdf_path, pdf_url = clarify_path_or_url(path_or_url=pdf_uri)  # pyright: ignore
        ocr_output: OcrOutput
        if pdf_url:
            ocr_output = await self.extract_from_pdf_url(
                pdf_url=pdf_url,
            )
        else:  # pdf_path must be provided based on validation
            assert pdf_path is not None  # Type narrowing for mypy
            ocr_output = await self.extract_from_pdf_file(
                pdf_path=pdf_path,
            )
        if should_add_screenshots:
            ocr_output = await self.add_page_screenshots_to_ocr_output(
                pdf_uri=pdf_uri,
                ocr_output=ocr_output,
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

        # TODO: set proper image format
        ocr_response = await self.mistral_client.ocr.process_async(
            model=self.ocr_engine.ocr_model_name,
            document={"type": "image_url", "image_url": f"data:image/jpeg;base64,{b64.decode('utf-8')}"},
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

    async def add_page_screenshots_to_ocr_output(
        self,
        pdf_uri: str,
        ocr_output: OcrOutput,
    ) -> OcrOutput:
        screenshot_uris: List[str] = []
        pdf_path, pdf_url = clarify_path_or_url(pdf_uri)
        # TODO: use centralized / possibly online storage instead of local file system
        images = await render_pdf_pages_to_images(pdf_path=pdf_path, pdf_url=pdf_url, dpi=300)

        temp_directory_name = shortuuid.uuid()
        temp_directory_path = f"temp/{temp_directory_name}"
        ensure_path(temp_directory_path)

        # Save images to the folder and return their paths
        screenshot_uris = []
        for image_index, image in enumerate(images):
            image_path = f"{temp_directory_path}/page_{image_index}.png"
            image.save(image_path)
            screenshot_uris.append(image_path)
        for page_index, page in enumerate(ocr_output.pages.values()):
            screenshot_uri = screenshot_uris[page_index]
            page.screenshot = OcrExtractedImage(uri=screenshot_uri)
        return ocr_output
