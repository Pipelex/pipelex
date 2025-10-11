from typing import Union

from pydantic import Field

from pipelex.tools.config.config_model import ConfigModel


class OcrSetting(ConfigModel):
    ocr_handle: str
    max_nb_images: int | None = Field(default=None, ge=0)
    image_min_size: int | None = Field(default=None, ge=0)

    def desc(self) -> str:
        return f"OcrSetting(ocr_handle={self.ocr_handle}, max_nb_images={self.max_nb_images}, image_min_size={self.image_min_size})"


OcrChoice = Union[OcrSetting, str]
