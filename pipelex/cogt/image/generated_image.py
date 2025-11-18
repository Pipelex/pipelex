from pipelex.tools.typing.pydantic_utils import CustomBaseModel


class GeneratedImage(CustomBaseModel):
    # TODO: add image_format
    # image_format: str = "jpeg"
    url: str
    width: int
    height: int
