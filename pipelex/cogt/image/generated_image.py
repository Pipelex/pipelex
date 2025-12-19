from pydantic import model_validator

from pipelex.tools.typing.pydantic_utils import CustomBaseModel
from pipelex.types import Self


class GeneratedImageRawDetails(CustomBaseModel):
    width: int
    height: int

    actual_url: str | None = None
    base64_str: str | None = None
    actual_url_or_prefixed_base64: str | None = None
    actual_bytes: bytes | None = None

    mime_type: str | None = None
    output_format: str | None = None

    @model_validator(mode="after")
    def validate_mime_type_or_output_format(self) -> Self:
        if self.mime_type is None and self.output_format is None:
            msg = "Either mime_type or output_format must be provided"
            raise ValueError(msg)
        return self


class GeneratedImageResolved(CustomBaseModel):
    url: str
    mime_type: str
    width: int
    height: int
