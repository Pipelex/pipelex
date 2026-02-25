from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class DocumentSummaryE2E(StructuredContent):
    """Summary of a document."""

    summary: str = Field(description="Concise summary of the document content")
    document_type: str = Field(description="Type of document (e.g., 'job offer', 'resume', 'article')")


class DocumentListAnalysisE2E(StructuredContent):
    """Analysis of multiple documents."""

    summary: str = Field(description="Summary of all documents")
    document_count: int = Field(description="Number of documents analyzed")


class MixedMediaAnalysisE2E(StructuredContent):
    """Analysis of documents and images together."""

    document_summary: str = Field(description="Summary of the document content")
    image_summary: str = Field(description="Description of the image content")
    can_see_both: bool = Field(description="Whether both the document and image content are visible")
