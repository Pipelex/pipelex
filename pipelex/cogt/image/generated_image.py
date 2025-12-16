from pipelex.tools.typing.pydantic_utils import CustomBaseModel


class GeneratedImage(CustomBaseModel):
    # oops: str
    url: str
    width: int
    height: int
    base_64_str: str | None = None
    content_type: str | None = None
