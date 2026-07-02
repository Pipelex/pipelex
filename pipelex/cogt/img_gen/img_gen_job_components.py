import re
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, BeforeValidator, Field, model_validator

from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.img_gen.img_gen_report import ImgGenTokensUsage
from pipelex.system.configuration.config_model import ConfigModel
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.types import Self, StrEnum


class AspectRatio(StrEnum):
    SQUARE = "square"
    LANDSCAPE_4_3 = "landscape_4_3"
    LANDSCAPE_3_2 = "landscape_3_2"
    LANDSCAPE_16_9 = "landscape_16_9"
    LANDSCAPE_21_9 = "landscape_21_9"
    LANDSCAPE_4_1 = "landscape_4_1"
    LANDSCAPE_8_1 = "landscape_8_1"
    PORTRAIT_3_4 = "portrait_3_4"
    PORTRAIT_2_3 = "portrait_2_3"
    PORTRAIT_9_16 = "portrait_9_16"
    PORTRAIT_9_21 = "portrait_9_21"
    PORTRAIT_1_4 = "portrait_1_4"
    PORTRAIT_1_8 = "portrait_1_8"


class SizeTier(StrEnum):
    """Portable image size classes.

    A tier promises a pixel class at the pipe's chosen aspect ratio, not identical
    pixel dimensions across providers: each provider maps the tier to its own grid
    or computed dimensions.
    """

    HALF_K = "0.5k"
    ONE_K = "1k"
    TWO_K = "2k"
    FOUR_K = "4k"

    @classmethod
    def quoted_tokens(cls) -> str:
        """Comma-separated quoted tier tokens, for error messages."""
        return ", ".join(f"'{tier}'" for tier in cls)


_EXACT_SIZE_PATTERN = re.compile(r"([1-9]\d*)x([1-9]\d*)")


def parse_img_gen_size(value: Any) -> Any:
    """Parse a string into a SizeTier token or an exact ImageSize; pass other values through."""
    if not isinstance(value, str):
        return value
    try:
        return SizeTier(value)
    except ValueError:
        pass
    if exact_match := _EXACT_SIZE_PATTERN.fullmatch(value):
        return ImageSize(width=int(exact_match.group(1)), height=int(exact_match.group(2)))
    msg = f"Invalid image size '{value}': expected a size tier ({SizeTier.quoted_tokens()}) or an exact size like '2048x1152'"
    raise ValueError(msg)


ImgGenSize: TypeAlias = Annotated[SizeTier | ImageSize, BeforeValidator(parse_img_gen_size)]


class Quality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class InputFidelity(StrEnum):
    LOW = "low"
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
    size: ImgGenSize | None = None
    background: Background = Field(strict=False)
    quality: Quality | None = Field(default=None, strict=False)
    input_fidelity: InputFidelity | None = Field(default=None, strict=False)
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
    size: ImgGenSize | None = None
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
            size=self.size,
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
    img_gen_tokens_usage: ImgGenTokensUsage | None = None
