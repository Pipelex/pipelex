from pydantic import BaseModel, Field

from pipelex.cogt.extract.bounding_box import BoundingBox


class GatewayExtractImage(BaseModel):
    """An extracted image with its base64 content and bounding box."""

    base64_str: str = Field(description="Base64-encoded image content")
    mime_type: str = Field(description="MIME type of the image")
    bounding_box: BoundingBox | None = Field(description="Bounding box coordinates of the image in the page", default=None)
    caption: str | None = Field(description="Caption text associated with the image", default=None)


class GatewayExtractPageResult(BaseModel):
    """Result for a single page of extracted markdown."""

    index: int = Field(description="The index of the page")
    markdown: str = Field(description="The markdown content of the page")
    images: list[GatewayExtractImage] = Field(description="The images on the page")


class GatewayExtractRequestParams(BaseModel):
    should_include_images: bool
