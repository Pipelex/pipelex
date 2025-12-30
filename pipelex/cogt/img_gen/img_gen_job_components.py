from typing import Literal

from pydantic import BaseModel, Field, model_validator

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.types import Self, StrEnum


class AspectRatio(StrEnum):
    SQUARE = "square"
    LANDSCAPE_4_3 = "landscape_4_3"
    LANDSCAPE_3_2 = "landscape_3_2"
    LANDSCAPE_16_9 = "landscape_16_9"
    LANDSCAPE_21_9 = "landscape_21_9"
    PORTRAIT_3_4 = "portrait_3_4"
    PORTRAIT_2_3 = "portrait_2_3"
    PORTRAIT_9_16 = "portrait_9_16"
    PORTRAIT_9_21 = "portrait_9_21"


class Quality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Background(StrEnum):
    TRANSPARENT = "transparent"
    OPAQUE = "opaque"
    AUTO = "auto"

    @property
    def is_certainly_transparent(self) -> bool:
        match self:
            case Background.TRANSPARENT:
                return True
            case Background.OPAQUE | Background.AUTO:
                return False


class ImgGenJobParams(BaseModel):
    aspect_ratio: AspectRatio = Field(strict=False)
    background: Background = Field(strict=False)
    quality: Quality | None = Field(default=None, strict=False)
    nb_steps: int | None = Field(default=None, gt=0)
    guidance_scale: float | None = Field(default=None, gt=0)
    is_moderated: bool | None = None
    safety_tolerance: int | None = Field(default=None, ge=1, le=6)
    is_raw: bool | None = None
    output_format: ImageFormat | None = Field(default=None, strict=False)
    seed: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_background_vs_output_format(self) -> Self:
        match self.background:
            case Background.OPAQUE | Background.AUTO:
                pass
            case Background.TRANSPARENT:
                if not self.output_format:
                    msg = "ImgGenJobParams cannot have a transparent background without setting output_format (to PNG)."
                    raise ValueError(msg)

                if not self.output_format.is_transparent_compatible:
                    msg = "ImgGenJobParams transparent background requires a transparency-compatible output format (PNG)."
                    raise ValueError(msg)
        return self


class ImgGenJobParamsDefaults(ConfigModel):
    aspect_ratio: AspectRatio = Field(strict=False)
    background: Background = Field(strict=False)
    quality: Quality | None = Field(default=None, strict=False)
    nb_steps: int | None = Field(default=None, gt=0)
    guidance_scale: float = Field(..., gt=0)
    is_moderated: bool | None = None
    safety_tolerance: int = Field(..., ge=1, le=6)
    is_raw: bool | None = None
    seed: int | Literal["auto"]

    def make_img_gen_job_params(self) -> ImgGenJobParams:
        seed: int | None
        if isinstance(self.seed, str) and self.seed == "auto":
            seed = None
        else:
            seed = self.seed
        output_format: ImageFormat | None = None
        if self.background.is_certainly_transparent:
            output_format = ImageFormat.PNG
        return ImgGenJobParams(
            aspect_ratio=self.aspect_ratio,
            background=self.background,
            quality=self.quality,
            nb_steps=self.nb_steps,
            guidance_scale=self.guidance_scale,
            is_moderated=self.is_moderated,
            safety_tolerance=self.safety_tolerance,
            is_raw=self.is_raw,
            output_format=output_format,
            seed=seed,
        )


class ImgGenJobConfig(ConfigModel):
    is_sync_mode: bool


########################################################################
# Outputs
########################################################################


class ImgGenJobReport(ConfigModel):
    pass
