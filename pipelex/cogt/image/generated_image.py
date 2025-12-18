from pipelex.tools.typing.pydantic_utils import CustomBaseModel


class GeneratedImageRawDetails(CustomBaseModel):
    width: int
    height: int

    actual_url: str | None = None
    base64_str: str | None = None
    actual_url_or_prefixed_base64: str | None = None
    actual_bytes: bytes | None = None

    mime_type: str | None = None
    output_format: str | None = None


class GeneratedImageResolved(CustomBaseModel):
    url: str
    mime_type: str | None = None
    width: int
    height: int
