import base64
from typing import Any

from typing_extensions import override

from pipelex import log
from pipelex.cogt.extract.extract_input import ExtractInputError
from pipelex.cogt.extract.extract_job import ExtractJob
from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.cogt.extract.extract_worker_abstract import ExtractWorkerAbstract
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.hub import get_storage_provider
from pipelex.reporting.reporting_protocol import ReportingProtocol
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from pipelex.tools.pdf.pypdfium2_renderer import PdfInput, pypdfium2_renderer
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)
from pipelex.tools.uri.uri_resolver import resolve_uri


class Pypdfium2Worker(ExtractWorkerAbstract):
    def __init__(
        self,
        extra_config: dict[str, Any],
        inference_model: InferenceModelSpec,
        reporting_delegate: ReportingProtocol | None = None,
    ):
        super().__init__(extra_config=extra_config, inference_model=inference_model, reporting_delegate=reporting_delegate)

    async def _resolve_pdf_uri(self, pdf_uri: str) -> PdfInput:
        """Resolve a PDF URI to PdfInput (path or bytes).

        Handles all URI types at the worker level, converting to a format
        that pypdfium2 can directly consume.

        Args:
            pdf_uri: URI string (local path, HTTP URL, pipelex-storage://, or data: URL)

        Returns:
            PdfInput: path string for local files, bytes for remote/storage/base64
        """
        pdf_input: PdfInput
        resolved_uri = resolve_uri(pdf_uri)
        match resolved_uri:
            case ResolvedHttpUrl():
                pdf_input = await fetch_file_from_url_httpx(url=resolved_uri.url)
            case ResolvedLocalPath():
                pdf_input = resolved_uri.path
            case ResolvedPipelexStorage():
                storage = get_storage_provider()
                pdf_input = await storage.load(uri=resolved_uri.storage_uri)
            case ResolvedBase64DataUrl():
                pdf_input = base64.b64decode(resolved_uri.base64_data)
        return pdf_input

    @override
    async def _extract_pages(
        self,
        extract_job: ExtractJob,
    ) -> ExtractOutput:
        if extract_job.extract_input.image_uri:
            msg = "Pypdfium2 only extracts text from PDFs, not from images"
            raise NotImplementedError(msg)

        pdf_uri = extract_job.extract_input.document_uri
        if not pdf_uri:
            msg = "No PDF URI provided in ExtractJob"
            raise ExtractInputError(msg)

        # Resolve storage/base64 URIs at worker level; HTTP/local paths pass through
        pdf_input = await self._resolve_pdf_uri(pdf_uri)

        # max_nb_images: None=unlimited, 0=no images, N=limit to N images
        max_nb_images = extract_job.job_params.max_nb_images
        should_extract_images = max_nb_images is None or max_nb_images > 0

        if should_extract_images:
            all_page_images = await pypdfium2_renderer.extract_embedded_images_from_pdf(pdf_input=pdf_input)
        else:
            all_page_images = {}

        all_page_texts = await pypdfium2_renderer.extract_text_from_pdf_pages(pdf_input=pdf_input)
        pages: dict[int, Page] = {}
        total_images_count = 0

        for page_index, page_text in enumerate(all_page_texts):
            page_number = page_index + 1
            if should_extract_images and page_number in all_page_images:
                page_images = all_page_images[page_number]
                # Apply truncation if max_nb_images is set
                if max_nb_images is not None:
                    remaining_slots = max_nb_images - total_images_count
                    if remaining_slots <= 0:
                        page_images = []
                    elif len(page_images) > remaining_slots:
                        original_count = len(page_images)
                        page_images = page_images[:remaining_slots]
                        log.warning(
                            f"Pypdfium2 extracted {original_count} images on page {page_number}, "
                            f"truncated to {len(page_images)} (max_nb_images={max_nb_images})"
                        )
                total_images_count += len(page_images)
                pages[page_number] = Page(text=page_text, extracted_images=page_images)
            else:
                pages[page_number] = Page(text=page_text)

        if max_nb_images is not None and total_images_count < sum(len(imgs) for imgs in all_page_images.values()):
            log.warning(f"Pypdfium2 does not support native image limiting. Extracted all images then truncated to {max_nb_images}.")

        return ExtractOutput(pages=pages)
