from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent


class FundamentalsDoc(StructuredContent):
    project_overview: str | None = Field(
        None,
        description="Mission, key features, architecture diagram, demo links",
    )
    core_concepts: dict[str, str] | None = Field(
        None,
        description=(
            "Names and definitions for project-specific terms, acronyms, data model names, background knowledge, business rules, domain entities"
        ),
    )
    repository_map: str | None = Field(
        None,
        description="Directory layout explanation and purpose of each folder",
    )


class DocumentationConcept(StructuredContent):
    """A specialized documentation concept that extends FundamentalsDoc."""

    title: str = Field(..., description="Title of the documentation")
    sections: list[str] = Field(default_factory=list, description="List of section names")
    last_updated: str | None = Field(None, description="Last update timestamp")


class MultiMediaConcept(StructuredContent):
    """A concept that combines text and images."""

    text_content: str = Field(..., description="The text content")
    image_urls: list[str] = Field(default_factory=list, description="List of image URLs")
    caption: str | None = Field(None, description="Optional caption for the content")


class IndependentConcept(StructuredContent):
    """An independent concept with its own structure."""

    unique_field: str = Field(..., description="A unique field for this concept")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata dictionary")
