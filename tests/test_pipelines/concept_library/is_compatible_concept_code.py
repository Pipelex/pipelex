from typing import Dict, List, Optional

from pydantic import Field

from pipelex.core.stuffs.stuff_content import StructuredContent


class FundamentalsDoc(StructuredContent):
    project_overview: Optional[str] = Field(
        None,
        description="Mission, key features, architecture diagram, demo links",
    )
    core_concepts: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "Names and definitions for project-specific terms, acronyms, data model names, background knowledge, business rules, domain entities"
        ),
    )
    repository_map: Optional[str] = Field(
        None,
        description="Directory layout explanation and purpose of each folder",
    )


class DocumentationConcept(StructuredContent):
    """A specialized documentation concept that extends FundamentalsDoc."""

    title: str = Field(..., description="Title of the documentation")
    sections: List[str] = Field(default_factory=list, description="List of section names")
    last_updated: Optional[str] = Field(None, description="Last update timestamp")


class MultiMediaConcept(StructuredContent):
    """A concept that combines text and images."""

    text_content: str = Field(..., description="The text content")
    image_urls: List[str] = Field(default_factory=list, description="List of image URLs")
    caption: Optional[str] = Field(None, description="Optional caption for the content")


class IndependentConcept(StructuredContent):
    """An independent concept with its own structure."""

    unique_field: str = Field(..., description="A unique field for this concept")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Metadata dictionary")
