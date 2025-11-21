from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class BasicDescription(StructuredContent):
    """Basic description of the image."""

    description: str = Field(description="Concise description of the image")


class VisionAnalysis(StructuredContent):
    """Structured analysis of visual content from an image."""

    main_subject: str = Field(description="The primary subject or focus of the image")
    category: str = Field(description="The category of the image")
    description: str = Field(description="Concise description of the image")
