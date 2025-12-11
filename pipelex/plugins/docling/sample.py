from __future__ import annotations

from typing import Any

from docling.document_converter import DocumentConverter
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer, MarkdownParams

from pipelex import pretty_print_md

PDF_PATH = "tests/data/documents/Job-Offer-Scan.pdf"


def extract_pdf_to_markdown_pages(pdf_path: str) -> list[dict[str, Any]]:
    """Convert a PDF to markdown using Docling, page by page.

    Returns a list of pages, each with markdown content.
    """
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    doc = result.document

    pages_output: list[dict[str, Any]] = []

    # doc.pages is a dictionary where keys are page numbers (1-based)
    # We iterate over the page numbers to serialize each page individually
    for page_no in sorted(doc.pages.keys()):
        # Create a serializer that targets only the specific page
        page_number_set = {page_no}
        params = MarkdownParams(pages=page_number_set)
        serializer = MarkdownDocSerializer(doc=doc, params=params)

        # Serialize to markdown
        md_content = serializer.serialize().text

        pages_output.append(
            {
                "page_number": page_no,
                "markdown": md_content,
            }
        )

    return pages_output


if __name__ == "__main__":
    pages = extract_pdf_to_markdown_pages(PDF_PATH)

    for page in pages:
        pretty_print_md(page["markdown"], title=f"Page {page['page_number']}")
