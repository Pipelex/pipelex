import json
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pytest

from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.uri.uri_bytes import load_bytes_from_any_uri

PLAYGROUND_DIR = Path("tests/e2e/pipelex/pipes/pipe_operators/pipe_doc_gen")


def _inputs(relative_path: str) -> dict[str, Any]:
    inputs: dict[str, Any] = json.loads((PLAYGROUND_DIR / relative_path).read_text(encoding="utf-8"))
    return inputs


async def _print(*, bundle_dir: str, pipe_code: str, inputs_file: str) -> tuple[DocumentContent, list[str]]:
    """Run one PipeDocGen step alone, and return its document with the text of each page."""
    result = await PipelexMTHDSProtocol(library_dirs=[str(PLAYGROUND_DIR / bundle_dir)]).execute(pipe_code=pipe_code, inputs=_inputs(inputs_file))
    document = result.pipe_output.main_stuff_as(content_type=DocumentContent)
    pdf_bytes = await load_bytes_from_any_uri(document.url, storage_provider=get_storage_provider())
    assert pdf_bytes.startswith(b"%PDF-")
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        page_texts: list[str] = []
        for page_index in range(len(pdf)):
            page_texts.append(pdf[page_index].get_textpage().get_text_bounded())  # pyright: ignore[reportUnknownMemberType]
    finally:
        pdf.close()
    return document, page_texts


@pytest.mark.asyncio(loop_scope="class")
class TestPipeDocGenPlayground:
    async def test_the_invoice_prints_over_several_pages_from_its_structure(self) -> None:
        document, page_texts = await _print(bundle_dir="invoice", pipe_code="render_invoice_pdf", inputs_file="invoice/inputs.json")

        assert document.filename == "invoice-INV-2026-0142.pdf"
        assert document.mime_type == "application/pdf"
        assert len(page_texts) > 1
        assert "INV-2026-0142" in page_texts[0]
        assert "Evotis S.A.S." in page_texts[0]
        assert f"Page 1 of {len(page_texts)}" in page_texts[0]
        assert f"Page {len(page_texts)} of {len(page_texts)}" in page_texts[-1]
        # The table's header row repeats on every page it runs over.
        assert "Description" in page_texts[1]

    async def test_the_markdown_report_prints_formatted(self) -> None:
        document, page_texts = await _print(bundle_dir="report", pipe_code="render_report_pdf", inputs_file="report/render_inputs.json")

        assert document.filename == "report.pdf"
        full_text = "\n".join(page_texts)
        assert "Quarterly review of invoice automation" in full_text
        assert "**" not in full_text
        assert "# Quarterly" not in full_text
        assert "<script>" in full_text
        assert "confidence_threshold = 0.9" in full_text
        assert "```" not in full_text
        assert "the automation dashboard" in full_text
        assert "](https://" not in full_text
