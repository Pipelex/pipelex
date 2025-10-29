from typing import Any

from google import genai
from google.genai import types
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ExtractCapabilityError, SdkTypeError
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.extract.extract_worker_factory import ExtractWorkerFactory
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.google.google_factory import GoogleFactory
from pipelex.plugins.pypdfium2.pypdfium2_worker import Pypdfium2Worker
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.base_64_utils import load_binary_as_base64_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64
from pipelex.tools.misc.path_utils import clarify_path_or_url


class GoogleExtractWorker(ExtractWorkerAbstract):
    def __init__(
        self,
        sdk_instance: genai.Client,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(
            extra_config=extra_config,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )
        genai_client: genai.Client = sdk_instance
        self.genai_async_client = genai_client.aio

        self.pypdfium2_worker = ExtractWorkerFactory.make_extract_worker(
            inference_model=InferenceModelSpec(
                backend_name="internal",
                name="pypdfium2-extract-text",
                sdk="pypdfium2",
                model_id="pypdfium2",
                inputs=["text"],
                outputs=["text"],
            ),
        )

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
            msg = "Captioning is not implemented for Google OCR."
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
            msg = "Captioning is not implemented for Google OCR."
            raise ExtractCapabilityError(msg)
        if should_include_page_views:
            log.verbose("Page views are not implemented for Google OCR.")
            # TODO: use a model capability flag to check possibility before asking for it
            # it it's asked and not available, raise
            # the caller will be responsible to get the page views using other solution if needed
            # raise OcrCapabilityError("Page views are not implemented for Google OCR.")
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
