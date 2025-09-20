from typing import Optional, Union

from pydantic import Field

from pipelex.tools.config.config_model import ConfigModel


class OcrSetting(ConfigModel):
    ocr_handle: str
    # should_include_images: bool
    max_nb_images: Optional[int] = Field(default=None, ge=0)
    image_min_size: Optional[int] = Field(default=None, ge=0)

    # def make_ocr_job_params(self) -> OcrJobParams:
    #     return OcrJobParams(
    #         should_include_images=self.should_include_images,
    #         max_nb_images=self.max_nb_images,
    #         image_min_size=self.image_min_size,
    #     )

    # def desc(self) -> str:
    #     return (
    #         f"OcrSetting(ocr_handle={self.ocr_handle}, should_include_images={self.should_include_images}, "
    #         f"max_nb_images={self.max_nb_images}, image_min_size={self.image_min_size})"
    # )
    def desc(self) -> str:
        return f"OcrSetting(ocr_handle={self.ocr_handle}, max_nb_images={self.max_nb_images}, image_min_size={self.image_min_size})"


OcrChoice = Union[OcrSetting, str]
