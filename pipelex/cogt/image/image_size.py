from pydantic import Field

from pipelex.tools.typing.pydantic_utils import CustomBaseModel


class ImageSize(CustomBaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
