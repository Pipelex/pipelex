from typing import Any

from typing_extensions import override

from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer


class Pypdfium2Worker(ExtractWorkerAbstract):
    def __init__(
        self,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(extra_config=extra_config, inference_model=inference_model, reporting_delegate=reporting_delegate)

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        if extract_job.extract_input.image_uri:
            msg = "Pypdfium2 only extracts text from PDFs, not from images"
            raise NotImplementedError(msg)

        pdf_uri = extract_job.extract_input.pdf_uri
        if not pdf_uri:
            msg = "No PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)

        all_page_images = await pypdfium2_renderer.extract_embedded_images_from_pdf_uri(pdf_uri=pdf_uri)

        all_page_texts = await pypdfium2_renderer.extract_text_from_pdf_pages_from_uri(pdf_uri=pdf_uri)
        pages: dict[int, Page] = {}
        for page_index, page_text in enumerate(all_page_texts):
            pages[page_index + 1] = Page(text=page_text, extracted_images=all_page_images[page_index + 1])
        return ExtractOutput(pages=pages)
