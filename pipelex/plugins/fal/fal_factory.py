from typing import Any, cast

from pydantic import ValidationError

from pipelex import pretty_print
from pipelex.cogt.exceptions import ImgGenGenerationError
from pipelex.cogt.image.generated_image import GeneratedImage


class FalFactory:
    @classmethod
    def make_generated_image(cls, fal_result: dict[str, Any]) -> GeneratedImage:
        generated_image_list = cls.make_generated_image_list(fal_result=fal_result)
        if len(generated_image_list) != 1:
            msg = f"Expected 1 image, got {len(generated_image_list)}"
            raise ImgGenGenerationError(msg)
        return generated_image_list[0]

    @classmethod
    def make_generated_image_list(cls, fal_result: dict[str, Any]) -> list[GeneratedImage]:
        return cls._unpack_fal_result(fal_result=fal_result)

    @classmethod
    def _unpack_fal_result(cls, fal_result: dict[str, Any]) -> list[GeneratedImage]:
        generated_image_list: list[GeneratedImage] = []
        try:
            image_dicts = fal_result["images"]
            if not isinstance(image_dicts, list):
                msg = f"Expected 'images' to be a list, got {type(image_dicts).__name__}"
                raise ImgGenGenerationError(msg)
            image_dicts = cast("list[dict[str, Any]]", image_dicts)
            for image_dict in image_dicts:
                pretty_print(image_dict, title="image_dict")
                generated_image = GeneratedImage(
                    url=image_dict["url"],
                    width=image_dict["width"],
                    height=image_dict["height"],
                    content_type=image_dict["content_type"],
                )
                generated_image_list.append(generated_image)
        except (KeyError, TypeError, ValidationError) as exc:
            msg = f"Failed to parse image data from fal response: {exc}"
            raise ImgGenGenerationError(msg) from exc

        return generated_image_list
