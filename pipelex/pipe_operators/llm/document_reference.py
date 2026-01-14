"""Data structures for representing document references in LLM prompt templates.

These models describe how documents are referenced in templates and guide
the document resolution process at runtime.
"""

from pydantic import BaseModel, Field
from typing_extensions import override

from pipelex.types import StrEnum


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
