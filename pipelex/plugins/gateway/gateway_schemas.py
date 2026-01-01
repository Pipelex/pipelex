from __future__ import annotations

from pydantic import BaseModel, Field


class GatewayExtractPageResult(BaseModel):
    """Result for a single page of extracted markdown."""

    index: int = Field(description="The index of the page")
    markdown: str = Field(description="The markdown content of the page")
    images: list[str] = Field(description="The images on the page")


class GatewayExtractRequestParams(BaseModel):
    should_include_images: bool
