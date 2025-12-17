from pipelex.tools.typing.pydantic_utils import CustomBaseModel


class GeneratedImageRawDetails(CustomBaseModel):
    width: int
    height: int

    actual_url: str | None = None
    base64_str: str | None = None
    actual_url_or_prefixed_base64: str | None = None
    actual_bytes: bytes | None = None

    content_type: str | None = None

    @property
    def url(self) -> str:
        return self.actual_url or ""


class GeneratedImageResolved(CustomBaseModel):
    url: str
    prefixed_base64_url: str | None = None
    content_type: str | None = None
    width: int
    height: int
