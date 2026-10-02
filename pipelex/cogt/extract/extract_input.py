from typing import Self

from pydantic import BaseModel, model_validator

from pipelex.cogt.extract.exceptions import ExtractInputError
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list
from pipelex.tools.uri.uri_read_scope import UriReference


class ExtractInput(BaseModel):
    image_uri: str | None = None
    document_uri: str | None = None

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
