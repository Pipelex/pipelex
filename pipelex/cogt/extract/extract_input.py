from pydantic import BaseModel, model_validator

from pipelex.cogt.exceptions import CogtError
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list
from pipelex.types import Self


class ExtractInputError(CogtError):
    pass


class ExtractInput(BaseModel):
    image_uri: str | None = None
    pdf_uri: str | None = None

    @model_validator(mode="after")
    def validate_at_exactly_one_input(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["image_uri", "pdf_uri"]):
            msg = "Exactly one of 'image_uri' or 'pdf_uri' must be provided"
            raise ExtractInputError(msg)
        return self
