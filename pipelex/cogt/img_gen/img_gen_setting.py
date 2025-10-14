from typing import Union

from pydantic import Field, model_validator

from pipelex.cogt.exceptions import ImgGenSettingsValidationError
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import Self


class ImgGenSetting(ConfigModel):
    model: str
    quality: Quality | None = Field(default=None, strict=False)
    nb_steps: int | None = Field(default=None, gt=0)
    guidance_scale: float | None = Field(default=None, gt=0)
    is_moderated: bool = False
    safety_tolerance: int | None = Field(default=None, ge=1, le=6)

    @model_validator(mode="after")
    def validate_quality_or_nb_steps(self) -> Self:
        if self.quality is not None and self.nb_steps is not None:
            msg = "ImgGenSetting cannot have both 'quality' and 'nb_steps' specified. Use one or the other."
            raise ImgGenSettingsValidationError(msg)
        return self

    def desc(self) -> str:
        return (
            f"ImgGenSetting(img_gen_handle={self.model}, quality={self.quality}, "
            f"nb_steps={self.nb_steps}, guidance_scale={self.guidance_scale}, "
            f"is_moderated={self.is_moderated}, safety_tolerance={self.safety_tolerance})"
        )


ImgGenModelChoice = Union[ImgGenSetting, str]
