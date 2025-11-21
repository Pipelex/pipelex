from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class DocumentInput(StructuredContent):
    text: str = Field(..., description="The text content of the document")


class LengthAnalysis(StructuredContent):
    analysis: str = Field(..., description="Analysis of document length and structure")


class ContentAnalysis(StructuredContent):
    analysis: str = Field(..., description="Analysis of document content and themes")


class CombinedAnalysis(StructuredContent):
    length_result: LengthAnalysis = Field(..., description="Length analysis results")
    content_result: ContentAnalysis = Field(..., description="Content analysis results")
