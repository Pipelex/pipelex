import asyncio
from typing import Any

from typing_extensions import override

from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.plugins.docling.docling_factory import DoclingFactory
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.path_utils import clarify_path_or_url


class DoclingExtractWorker(ExtractWorkerAbstract):
    def __init__(
        self,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(
            extra_config=extra_config,
            inference_model=inference_model,
            reporting_delegate=reporting_delegate,
        )

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        if extract_job.extract_input.image_uri:
            msg = "Docling extract worker only supports PDF extraction, not images"
            raise NotImplementedError(msg)

        if pdf_uri := extract_job.extract_input.pdf_uri:
            pdf_path, pdf_url = clarify_path_or_url(path_or_uri=pdf_uri)
            extract_output: ExtractOutput
            if pdf_url:
                extract_output = await self._extract_from_pdf_url(pdf_url=pdf_url)
            else:
                assert pdf_path is not None
                extract_output = await self._extract_from_pdf_file(pdf_path=pdf_path)
        else:
            msg = "No PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)

        return extract_output

    async def _extract_from_pdf_url(self, pdf_url: str) -> ExtractOutput:
        """Extract text from a PDF URL.

        Docling supports URLs directly through its DocumentConverter.
        """
        # Run synchronous Docling conversion in a thread pool to avoid blocking
        conversion_result = await asyncio.to_thread(DoclingFactory.convert_pdf, pdf_url)
        return DoclingFactory.make_extract_output_from_docling_document(doc=conversion_result.document)

    async def _extract_from_pdf_file(self, pdf_path: str) -> ExtractOutput:
        """Extract text from a local PDF file."""
        # Run synchronous Docling conversion in a thread pool to avoid blocking
        conversion_result = await asyncio.to_thread(DoclingFactory.convert_pdf, pdf_path)
        return DoclingFactory.make_extract_output_from_docling_document(doc=conversion_result.document)
