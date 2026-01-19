"""Data structures for representing image references in LLM prompt templates.

These models describe how images are referenced in templates and guide
the image resolution process at runtime.
"""

from pydantic import BaseModel, Field
from typing_extensions import override

from pipelex.types import StrEnum


class ImageReferenceKind(StrEnum):
    """The kind of image reference in a template."""

    DIRECT = "direct"
    """Direct reference to an ImageContent variable, e.g., {{ portrait }}"""

    DIRECT_LIST = "direct_list"
    """Direct reference to a ListContent of ImageContent, e.g., {{ photos }}"""

    NESTED = "nested"
    """Reference with | with_images filter for nested image extraction,
    e.g., {{ document | with_images }}"""


class ImageReference(BaseModel):
    """Represents an image reference found in a template.

    This model captures:
    - The variable path referenced in the template
    - The kind of reference (direct, list, or nested with filter)
    - For nested references, the paths to nested images within the structure
    """

    variable_path: str = Field(description="The variable path referenced in the template, e.g., 'portrait', 'doc.cover', 'pages'")

    kind: ImageReferenceKind = Field(description="The kind of image reference")

    nested_image_paths: list[str] | None = Field(
        default=None,
        description="For NESTED kind: relative paths to images within the structure, e.g., ['text_and_images.images', 'page_view']",
    )

    @override
    def __str__(self) -> str:
        match self.kind:
            case ImageReferenceKind.DIRECT:
                return f"ImageReference(DIRECT: {self.variable_path})"
            case ImageReferenceKind.DIRECT_LIST:
                return f"ImageReference(DIRECT_LIST: {self.variable_path})"
            case ImageReferenceKind.NESTED:
                nested_str = ", ".join(self.nested_image_paths or [])
                return f"ImageReference(NESTED: {self.variable_path} -> [{nested_str}])"
