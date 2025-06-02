from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

from pipelex.tools.config.models import ConfigModel
from pipelex.types import StrEnum


class AspectRatio(StrEnum):
    SQUARE = "square"
    LANDSCAPE_4_3 = "landscape_4_3"
    LANDSCAPE_3_2 = "landscape_3_2"
    LANDSCAPE_16_9 = "landscape_16_9"
    LANDSCAPE_21_9 = "landscape_21_9"
    PORTRAIT_3_4 = "portrait_4_3"
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


class ImggJobParams(BaseModel):
    aspect_ratio: AspectRatio = Field(strict=False)
    background: Background = Field(strict=False)
    quality: Optional[Quality] = Field(default=None, strict=False)
    nb_steps: Optional[int] = Field(default=None, gt=0)
    guidance_scale: float = Field(..., gt=0)
    is_moderated: bool
    safety_tolerance: int = Field(..., ge=1, le=6)
    is_raw: bool
    output_format: OutputFormat = Field(strict=False)
    seed: Optional[int] = Field(None, ge=0)


class ImggJobParamsDefaults(ConfigModel):
    aspect_ratio: AspectRatio = Field(strict=False)
    background: Background = Field(strict=False)
    quality: Optional[Quality] = Field(default=None, strict=False)
    nb_steps: Optional[int] = Field(default=None, gt=0)
    guidance_scale: float = Field(..., gt=0)
    is_moderated: bool
    safety_tolerance: int = Field(..., ge=1, le=6)
    is_raw: bool
    output_format: OutputFormat = Field(strict=False)
    seed: Union[int, Literal["auto"]]

    def make_imgg_job_params(self) -> ImggJobParams:
        seed: Optional[int]
        if isinstance(self.seed, str) and self.seed == "auto":
            seed = None
        else:
            seed = self.seed
        return ImggJobParams(
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


class ImggJobConfig(ConfigModel):
    is_sync_mode: bool


########################################################################
### Outputs
########################################################################


class ImggJobReport(ConfigModel):
    pass
