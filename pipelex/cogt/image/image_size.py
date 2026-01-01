from pipelex.tools.typing.pydantic_utils import CustomBaseModel


class ImageSize(CustomBaseModel):
    width: int
    height: int
