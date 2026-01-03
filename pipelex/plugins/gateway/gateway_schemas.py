from pydantic import BaseModel, Field

from pipelex.cogt.extract.bounding_box import BoundingBox


class GatewayExtractRequestParams(BaseModel):
    should_include_images: bool


class GatewayExtractImageAzure(BaseModel):
    """An extracted image with its base64 content and bounding box."""

    base64_str: str = Field(description="Base64-encoded image content")
    mime_type: str = Field(description="MIME type of the image")
    bounding_box: BoundingBox | None = Field(description="Bounding box coordinates of the image in the page", default=None)
    caption: str | None = Field(description="Caption text associated with the image", default=None)


class GatewayExtractPageAzure(BaseModel):
    """Result for a single page extracted by Azure Doc Intel."""

    index: int = Field(description="The index of the page")
    markdown: str = Field(description="The markdown content of the page")
    images: list[GatewayExtractImageAzure] = Field(description="The images on the page")


class GatewayExtractImageMistral(BaseModel):
    """An extracted image with its base64 content and bounding box."""

    id: str | None = Field(description="The ID of the image", default=None)
    top_left_x: int | None = Field(description="The X coordinate of the top left corner of the image", default=None)
    top_left_y: int | None = Field(description="The Y coordinate of the top left corner of the image", default=None)
    bottom_right_x: int | None = Field(description="The X coordinate of the bottom right corner of the image", default=None)
    bottom_right_y: int | None = Field(description="The Y coordinate of the bottom right corner of the image", default=None)
    image_base64: str | None = Field(description="Base64-encoded image content", default=None)
    image_annotation: str | None = Field(description="Annotation text associated with the image", default=None)


class GatewayExtractPageMistral(BaseModel):
    """Result for a single page extracted by Mistral Doc AI."""

    index: int = Field(description="The index of the page")
    markdown: str = Field(description="The markdown content of the page")
    images: list[GatewayExtractImageMistral] = Field(description="The images on the page")
