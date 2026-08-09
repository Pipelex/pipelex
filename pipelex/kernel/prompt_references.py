"""How a prompt names the images and documents it wants out of working memory.

These describe a *resolution* — "the variable at this path holds an `ImageContent`, fetch it and
register it" — which is execution semantics, not language. They live here rather than under
`pipe_operators/` because the kernel is what resolves them, and a runtime-layer module may not
import an interpreter-layer one; the blueprints that parse `.mthds` into them import upward, which
is the sanctioned direction. Same move `core/` made with `ConceptProviderAbstract`: the semantics
migrate to the layer that owns them, and the language artifact keeps its parse-and-validate role.
"""

from enum import StrEnum

from pydantic import BaseModel, Field
from typing_extensions import override


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


class DocumentReferenceKind(StrEnum):
    """The kind of document reference in a template."""

    DIRECT = "direct"
    """Direct reference to a DocumentContent variable, e.g., {{ report }}"""

    DIRECT_LIST = "direct_list"
    """Direct reference to a ListContent of DocumentContent, e.g., {{ documents }}"""


class DocumentReference(BaseModel):
    """Represents a document reference found in a template.

    This model captures:
    - The variable path referenced in the template
    - The kind of reference (direct or list)
    """

    variable_path: str = Field(description="The variable path referenced in the template, e.g., 'report', 'submission.pdf', 'documents'")

    kind: DocumentReferenceKind = Field(description="The kind of document reference")

    @override
    def __str__(self) -> str:
        match self.kind:
            case DocumentReferenceKind.DIRECT:
                return f"DocumentReference(DIRECT: {self.variable_path})"
            case DocumentReferenceKind.DIRECT_LIST:
                return f"DocumentReference(DIRECT_LIST: {self.variable_path})"
