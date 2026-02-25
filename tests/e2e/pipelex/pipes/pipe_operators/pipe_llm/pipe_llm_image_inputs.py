from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class ImageDescriptionE2E(StructuredContent):
    """Description of an image."""

    description: str = Field(description="Concise description of the image")


class ImageListAnalysisE2E(StructuredContent):
    """Analysis of multiple images."""

    summary: str = Field(description="Summary of the images")
    image_count: int = Field(description="Number of images analyzed")


class PageDescriptionE2E(StructuredContent):
    """Description of a page."""

    description: str = Field(description="Description of the page content")
    can_see_image_content: bool = Field(
        description="Whether you can see and describe the actual visual content of any images (not just URLs or metadata)"
    )
