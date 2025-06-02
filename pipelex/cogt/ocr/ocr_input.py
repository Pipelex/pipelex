from typing import Optional

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from pipelex.cogt.exceptions import CogtError
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list


class OcrInputError(CogtError):
    pass


class OcrInput(BaseModel):
    image_uri: Optional[str] = None
    pdf_uri: Optional[str] = None

    @model_validator(mode="after")
    def validate_at_exactly_one_input(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["image_uri", "pdf_uri"]):
            raise OcrInputError("Exactly one of 'image_uri' or 'pdf_uri' must be provided")
        return self
