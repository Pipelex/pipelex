from typing import Annotated, Union

from pydantic import BeforeValidator, Field, model_validator

from pipelex.cogt.img_gen.img_gen_job_components import Quality
from pipelex.cogt.models.model_reference import ModelReference, parse_model_reference
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import Self


class ImgGenSettingValueError(ValueError):
    pass


class ImgGenSetting(ConfigModel):
    model: str
    quality: Quality | None = Field(default=None, strict=False)
    nb_steps: int | None = Field(default=None, gt=0)
    guidance_scale: float | None = Field(default=None, gt=0)
    # None means "no explicit choice": workers omit the moderation/safety-checker param so the provider's
    # own default applies (OpenAI gpt-image defaults to "auto", i.e. standard filtering)
    is_moderated: bool | None = None
    safety_tolerance: int | None = Field(default=None, ge=1, le=6)
    description: str | None = None

    @model_validator(mode="after")
    def validate_quality_or_nb_steps(self) -> Self:
        if self.quality is not None and self.nb_steps is not None:
            msg = (
                "ImgGenSetting cannot have both 'quality' and 'nb_steps' specified. Use one or the other."
                f"Quality: {self.quality}, nb_steps: {self.nb_steps}"
            )
            raise ImgGenSettingValueError(msg)
        return self

    def desc(self) -> str:
        return (
            f"ImgGenSetting(img_gen_handle={self.model}, quality={self.quality}, "
            f"nb_steps={self.nb_steps}, guidance_scale={self.guidance_scale}, "
            f"is_moderated={self.is_moderated}, safety_tolerance={self.safety_tolerance})"
        )


# ImgGenModelChoice accepts ImgGenSetting, ModelReference, or a string (which gets parsed to ModelReference)
# The BeforeValidator ensures that strings are automatically converted to ModelReference during validation
# ModelReference.model_serializer handles serialization back to the raw string value
ImgGenModelChoice = Union[
    ImgGenSetting,
    Annotated[str | ModelReference, BeforeValidator(parse_model_reference)],
]
