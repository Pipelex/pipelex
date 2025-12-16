from docling_core.transforms.serializer.markdown import MarkdownDocSerializer, MarkdownParams
from docling_core.types.doc.document import DoclingDocument

from pipelex.cogt.extract.extract_output import ExtractOutput, Page
from pipelex.plugins.docling.docling_sdk import DoclingSdk


class DoclingFactory:
    @classmethod
    def make_docling_sdk(cls) -> DoclingSdk:
        return DoclingSdk()

    @classmethod
    def make_extract_output_from_docling_document(
        cls,
        doc: DoclingDocument,
    ) -> ExtractOutput:
        """Convert a Docling document to ExtractOutput with markdown text per page.

        Args:
            doc: The Docling document from conversion result.

        Returns:
            ExtractOutput with pages dict (0-indexed).
        """
        pages: dict[int, Page] = {}

        # doc.pages is a dictionary where keys are page numbers (1-based in Docling)
        for page_no in sorted(doc.pages.keys()):
            # Create a serializer that targets only the specific page
            page_number_set = {page_no}
            params = MarkdownParams(pages=page_number_set)
            serializer = MarkdownDocSerializer(doc=doc, params=params)

            # Serialize to markdown
            md_content = serializer.serialize().text

            # Store as 0-indexed (page_no - 1) to match the convention used by other workers
            pages[page_no - 1] = Page(text=md_content)

        return ExtractOutput(pages=pages)
