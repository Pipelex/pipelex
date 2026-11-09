from typing import Final, Self

from pydantic import BaseModel, model_validator

from pipelex.cogt.extract.exceptions import ExtractInputError
from pipelex.cogt.inference.provider_name import ProviderName
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list
from pipelex.tools.uri.uri_read_scope import UriReference

# What draws a document's page views. A refusal names it as the model that cannot take the file, since the rule is the
# renderer's and holds whatever the extraction's own model reads.
PAGE_VIEWS_RENDERER: Final[str] = ProviderName.PYPDFIUM2.value

# The advice of a refusal to draw page views from a file known not to be a PDF.
PAGE_VIEWS_FILE_ADVICE: Final[str] = "Give a PDF, or remove page_views from the step."


class ExtractInput(BaseModel):
    """The file an extraction reads: an image or a document, with what is known of it.

    `mime_type` is the file's identified type, which run setup stamps on every file input, and
    `input_name` the input it came from, as a caller writes it (`transcripts[2]`), for messages.
    Both are `None` when unknown, and the worker then leaves the format to the provider.
    """

    image_uri: str | None = None
    document_uri: str | None = None
    mime_type: str | None = None
    input_name: str | None = None

    @model_validator(mode="after")
    def validate_at_exactly_one_input(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["image_uri", "document_uri"]):
            msg = "Exactly one of 'image_uri' or 'document_uri' must be provided"
            raise ExtractInputError(msg)
        return self

    def referenced_uris(self) -> list[UriReference]:
        """The URL a worker will read to extract: the image or the document."""
        uri_references: list[UriReference] = []
        if self.image_uri is not None:
            uri_references.append(UriReference(uri=self.image_uri, position="the image to extract"))
        if self.document_uri is not None:
            uri_references.append(UriReference(uri=self.document_uri, position="the document to extract"))
        return uri_references
