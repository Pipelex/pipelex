from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import field_validator, model_validator

from pipelex.cogt.exceptions import GeneratedImageError
from pipelex.cogt.image.image_size import ImageSize
from pipelex.tools.misc.base64_utils import extract_base64_str_from_base64_url_if_possible
from pipelex.tools.misc.image_utils import ImageFormat, pil_image_to_bytes
from pipelex.tools.typing.pydantic_utils import CustomBaseModel

if TYPE_CHECKING:
    from PIL import Image

    from pipelex.types import Self


class GeneratedImageRawDetails(CustomBaseModel):
    size: ImageSize | None

    actual_url: str | None = None
    base64_str: str | None = None
    actual_url_or_prefixed_base64: str | None = None
    actual_bytes: bytes | None = None

    mime_type: str | None = None
    image_format: str | None = None

    caption: str | None = None

    @field_validator("image_format", mode="before")
    @classmethod
    def validate_image_format(cls, image_format_str: str | None) -> str | None:
        if image_format_str:
            return ImageFormat(image_format_str).value
        else:
            return None

    @model_validator(mode="after")
    def validate_mime_type_or_image_format(self) -> Self:
        if self.mime_type:
            ImageFormat.raise_if_unsupported_mime_type(self.mime_type)
        elif self.actual_url_or_prefixed_base64 and (
            result := extract_base64_str_from_base64_url_if_possible(possibly_base64_url=self.actual_url_or_prefixed_base64)
        ):
            base64_str, base64_extracted_mime_type = result
            ImageFormat.raise_if_unsupported_mime_type(base64_extracted_mime_type)
            self.mime_type = base64_extracted_mime_type
            self.base64_str = base64_str
        elif self.image_format is None:
            msg = "Either mime_type or image_format must be provided"
            raise ValueError(msg)
        return self

    @classmethod
    def make_from_pil_image(cls, pil_image: Image.Image, image_format: ImageFormat) -> GeneratedImageRawDetails:
        try:
            width, height = pil_image.size
            actual_bytes = pil_image_to_bytes(pil_image=pil_image, image_format=image_format)
            return GeneratedImageRawDetails(
                size=ImageSize(width=width, height=height),
                actual_bytes=actual_bytes,
                image_format=image_format,
            )
        except (ValueError, OSError, AttributeError) as exc:
            msg = f"Failed to convert PIL image to GeneratedImageRawDetails: {exc}"
            raise GeneratedImageError(msg) from exc
