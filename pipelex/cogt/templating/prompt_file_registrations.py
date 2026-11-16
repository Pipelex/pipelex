"""The images and documents a prompt's operator registered, carried to the leaf that renders the prompt.

Prompt assembly (`pipelex.kernel.prompt_assembly.PromptFiles`) numbers every image and document a prompt references
before any template renders. Since prompts render in their content-generation leaf, which on a host runtime is an
activity, the registration happens in the operator, where working memory is, and its result travels to the leaf in
this shape: the leaf rebuilds the same registry from it, so the numbering it renders is the one the operator decided.
It carries no file's bytes, only the contents and documents the operator found, which name their files by URL.
"""

from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of


class PromptFileRegistrations(BaseModel):
    """The state of a prompt's file registry once every reference was registered and before any template rendered.

    Attributes:
        images: Every directly referenced image, in registry order, deduplicated by URL.
        image_registry_indices: Each directly referenced image's 0-based registry index, keyed by its variable path,
            a list's items keyed `album[1]`, `album[2]`.
        list_image_paths: The variable paths of the image lists the prompt references.
        documents: Each referenced document keyed by its variable path, in the order its token numbers it.
        list_document_paths: The variable paths of the document lists the prompt references.
    """

    model_config = ConfigDict(frozen=True)

    images: list[ImageContent] = Field(default_factory=empty_list_factory_of(ImageContent))
    image_registry_indices: dict[str, int] = Field(default_factory=dict)
    list_image_paths: list[str] = Field(default_factory=list)
    documents: dict[str, PromptDocument] = Field(default_factory=dict)
    list_document_paths: list[str] = Field(default_factory=list)

    def with_documents(self, *, documents: list[PromptDocument]) -> "PromptFileRegistrations":
        """The same registrations with each document replaced by the one at its position, such as its readable PDF.

        Raises:
            ValueError: The number of documents given is not the number registered.
        """
        if len(documents) != len(self.documents):
            msg = f"Replacing {len(self.documents)} registered prompt documents needs as many documents, got {len(documents)}."
            raise ValueError(msg)
        return self.model_copy(update={"documents": dict(zip(self.documents, documents, strict=True))})
