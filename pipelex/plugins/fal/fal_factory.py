from typing import Any, cast

from pydantic import ValidationError

from pipelex.cogt.exceptions import ImgGenGenerationError, InferenceErrorCategory
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind


class FalFactory:
    @classmethod
    def make_generated_image(cls, fal_result: dict[str, Any]) -> GeneratedImageRawDetails:
        generated_image_list = cls.make_generated_image_list(fal_result=fal_result)
        if len(generated_image_list) != 1:
            msg = f"Expected 1 image, got {len(generated_image_list)}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="FAL returned an unexpected number of images — try a different model",
                ),
                provider_metadata=None,
            )
        return generated_image_list[0]

    @classmethod
    def make_generated_image_list(cls, fal_result: dict[str, Any]) -> list[GeneratedImageRawDetails]:
        generated_image_list: list[GeneratedImageRawDetails] = []
        try:
            image_dicts = fal_result["images"]
            if not isinstance(image_dicts, list):
                msg = f"Expected 'images' to be a list, got {type(image_dicts).__name__}"
                raise ImgGenGenerationError(
                    msg,
                    error_category=InferenceErrorCategory.CONTENT,
                    user_action=UserAction(
                        kind=UserActionKind.CHANGE_INPUT,
                        detail="FAL returned an unexpected response shape — try a different model",
                    ),
                    provider_metadata=None,
                )
            image_dicts = cast("list[dict[str, Any]]", image_dicts)
            for image_dict in image_dicts:
                generated_image = GeneratedImageRawDetails(
                    actual_url_or_prefixed_base64=image_dict["url"],
                    size=ImageSize(width=image_dict["width"], height=image_dict["height"]),
                    mime_type=image_dict["content_type"],
                )
                generated_image_list.append(generated_image)
        except (KeyError, TypeError, ValidationError) as exc:
            msg = f"Failed to parse image data from fal response: {exc}"
            raise ImgGenGenerationError(
                msg,
                error_category=InferenceErrorCategory.CONTENT,
                user_action=UserAction(
                    kind=UserActionKind.CHANGE_INPUT,
                    detail="FAL returned a malformed image response — try a different model",
                ),
                provider_metadata=None,
            ) from exc

        return generated_image_list
