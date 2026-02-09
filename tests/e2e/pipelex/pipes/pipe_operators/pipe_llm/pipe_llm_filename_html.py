from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class InputDescriptionsE2E(StructuredContent):
    """Descriptions of image and document inputs."""

    image_description: str = Field(description="One-sentence description of the image")
    document_description: str = Field(description="One-sentence description of the document")
