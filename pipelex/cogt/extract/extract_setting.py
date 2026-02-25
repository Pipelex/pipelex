from typing import Annotated, Union

from pydantic import BeforeValidator, Field

from pipelex.cogt.models.model_reference import ModelReference, parse_model_reference
from pipelex.system.configuration.config_model import ConfigModel


class ExtractSetting(ConfigModel):
    model: str
    max_nb_images: int | None = Field(default=None, ge=0)
    image_min_size: int | None = Field(default=None, ge=0)
    description: str | None = None

    def desc(self) -> str:
        return f"OcrSetting(extract_handle={self.model}, max_nb_images={self.max_nb_images}, image_min_size={self.image_min_size})"


# ExtractModelChoice accepts ExtractSetting, ModelReference, or a string (which gets parsed to ModelReference)
# The BeforeValidator ensures that strings are automatically converted to ModelReference during validation
# ModelReference.model_serializer handles serialization back to the raw string value
ExtractModelChoice = Union[
    ExtractSetting,
    Annotated[str | ModelReference, BeforeValidator(parse_model_reference)],
]
