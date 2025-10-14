from typing import Union

from pydantic import Field

from pipelex.system.configuration.config_model import ConfigModel


class ExtractSetting(ConfigModel):
    model: str
    max_nb_images: int | None = Field(default=None, ge=0)
    image_min_size: int | None = Field(default=None, ge=0)

    def desc(self) -> str:
        return f"OcrSetting(extract_handle={self.model}, max_nb_images={self.max_nb_images}, image_min_size={self.image_min_size})"


ExtractModelChoice = Union[ExtractSetting, str]
