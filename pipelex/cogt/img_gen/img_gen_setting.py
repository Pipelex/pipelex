from typing import Optional, Union

from pydantic import Field, model_validator
from typing_extensions import Self

from pipelex.cogt.exceptions import ImgGenSettingsValidationError
from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.tools.config.config_model import ConfigModel


class ImgGenSetting(ConfigModel):
    img_gen_handle: str
    quality: Optional[Quality] = Field(default=None, strict=False)
    nb_steps: Optional[int] = Field(default=None, gt=0)
    guidance_scale: Optional[float] = Field(default=None, gt=0)
    is_moderated: bool = False
    safety_tolerance: Optional[int] = Field(default=None, ge=1, le=6)

    @model_validator(mode="after")
    def validate_quality_or_nb_steps(self) -> Self:
        if self.quality is not None and self.nb_steps is not None:
            raise ImgGenSettingsValidationError("ImgGenSetting cannot have both 'quality' and 'nb_steps' specified. Use one or the other.")
        return self

    def desc(self) -> str:
        return (
            f"ImgGenSetting(img_gen_handle={self.img_gen_handle}, quality={self.quality}, "
            f"nb_steps={self.nb_steps}, guidance_scale={self.guidance_scale}, "
            f"is_moderated={self.is_moderated}, safety_tolerance={self.safety_tolerance})"
        )


ImgGenChoice = Union[ImgGenSetting, str]
