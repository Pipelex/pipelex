from typing import Any

from typing_extensions import override

from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.path_utils import clarify_path_or_url
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
            msg = "Pypdfium2 only extracts text from PDFs, not images"
            raise NotImplementedError(msg)

        if pdf_uri := extract_job.extract_input.pdf_uri:
            pdf_path, pdf_url = clarify_path_or_url(path_or_uri=pdf_uri)
            extract_output: ExtractOutput
            if pdf_url:
                extract_output = await self.extract_from_pdf_url(
                    pdf_url=pdf_url,
                )
            else:  # pdf_path must be provided based on validation
                assert pdf_path is not None  # Type narrowing for mypy
                extract_output = await self.extract_from_pdf_file(
                    pdf_path=pdf_path,
                )
        else:
            msg = "No PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)
        return extract_output

    async def extract_from_pdf_url(
        self,
        pdf_url: str,
    ) -> ExtractOutput:
        page_texts = await pypdfium2_renderer.get_text_from_pdf_pages_from_uri(pdf_uri=pdf_url)
        pages: dict[int, Page] = {}
        for page_index, page_text in enumerate(page_texts):
            pages[page_index + 1] = Page(
                text=page_text,
            )
        return ExtractOutput(
            pages=pages,
        )

    async def extract_from_pdf_file(
        self,
        pdf_path: str,
    ) -> ExtractOutput:
        page_texts = await pypdfium2_renderer.get_text_from_pdf_pages(pdf_input=pdf_path)
        pages: dict[int, Page] = {}
        for page_index, page_text in enumerate(page_texts):
            pages[page_index + 1] = Page(
                text=page_text,
            )
        return ExtractOutput(
            pages=pages,
        )
