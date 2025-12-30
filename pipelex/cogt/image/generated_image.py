from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import model_validator

from pipelex.cogt.exceptions import GeneratedImageError
from pipelex.tools.misc.image_utils import ImageFormat, pil_image_to_bytes
from pipelex.tools.typing.pydantic_utils import CustomBaseModel

if TYPE_CHECKING:
    from PIL import Image

    from pipelex.types import Self


class GeneratedImageRawDetails(CustomBaseModel):
    width: int
    height: int

    actual_url: str | None = None
    base64_str: str | None = None
    actual_url_or_prefixed_base64: str | None = None
    actual_bytes: bytes | None = None

    mime_type: str | None = None
    output_format: str | None = None

    @model_validator(mode="after")
    def validate_mime_type_or_output_format(self) -> Self:
        if self.mime_type is None and self.output_format is None:
            msg = "Either mime_type or output_format must be provided"
            raise ValueError(msg)
        return self

    @classmethod
    def make_from_pil_image(cls, pil_image: Image.Image, output_format: ImageFormat) -> GeneratedImageRawDetails:
        try:
            width, height = pil_image.size
            actual_bytes = pil_image_to_bytes(pil_image=pil_image, image_format=output_format)
            return GeneratedImageRawDetails(
                width=width,
                height=height,
                actual_bytes=actual_bytes,
                output_format=output_format,
            )
        except (ValueError, OSError, AttributeError) as exc:
            msg = f"Failed to convert PIL image to GeneratedImageRawDetails: {exc}"
            raise GeneratedImageError(msg) from exc


class GeneratedImageResolved(CustomBaseModel):
    url: str
    mime_type: str
    width: int
    height: int
