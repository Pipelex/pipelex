from typing import Literal

from pydantic import BaseModel, Field

from pipelex.system.configuration.config_model import ConfigModel
from pipelex.types import StrEnum


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


class OutputFormat(StrEnum):
    PNG = "png"
    JPG = "jpg"
    WEBP = "webp"


class Quality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Background(StrEnum):
    TRANSPARENT = "transparent"
    OPAQUE = "opaque"
    AUTO = "auto"


class ImgGenJobParams(BaseModel):
    aspect_ratio: AspectRatio = Field(strict=False)
    background: Background = Field(strict=False)
    quality: Quality | None = Field(default=None, strict=False)
    nb_steps: int | None = Field(default=None, gt=0)
    guidance_scale: float | None = Field(default=None, gt=0)
    is_moderated: bool = False
    safety_tolerance: int | None = Field(default=None, ge=1, le=6)
    is_raw: bool
    output_format: OutputFormat = Field(strict=False)
    seed: int | None = Field(None, ge=0)


class ImgGenJobParamsDefaults(ConfigModel):
    aspect_ratio: AspectRatio = Field(strict=False)
    background: Background = Field(strict=False)
    quality: Quality | None = Field(default=None, strict=False)
    nb_steps: int | None = Field(default=None, gt=0)
    guidance_scale: float = Field(..., gt=0)
    is_moderated: bool
    safety_tolerance: int = Field(..., ge=1, le=6)
    is_raw: bool
    output_format: OutputFormat = Field(strict=False)
    seed: int | Literal["auto"]

    def make_img_gen_job_params(self) -> ImgGenJobParams:
        seed: int | None
        if isinstance(self.seed, str) and self.seed == "auto":
            seed = None
        else:
            seed = self.seed
        return ImgGenJobParams(
            aspect_ratio=self.aspect_ratio,
            background=self.background,
            quality=self.quality,
            nb_steps=self.nb_steps,
            guidance_scale=self.guidance_scale,
            is_moderated=self.is_moderated,
            safety_tolerance=self.safety_tolerance,
            is_raw=self.is_raw,
            output_format=self.output_format,
            seed=seed,
        )


class ImgGenJobConfig(ConfigModel):
    is_sync_mode: bool


########################################################################
### Outputs
########################################################################


class ImgGenJobReport(ConfigModel):
    pass
