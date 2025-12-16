from typing_extensions import override

from pipelex.cogt.image.generated_image import GeneratedImage
from pipelex.cogt.image.generated_image_factory_abstract import GeneratedImageFactoryAbstract


class GeneratedImageFactory(GeneratedImageFactoryAbstract):
    @override
    def make_generated_image(
        self,
        url: str | None = None,
        width: int | None = None,
        height: int | None = None,
        base_64_str: str | None = None,
        content_type: str | None = None,
    ) -> GeneratedImage:
        return GeneratedImage(
            url=url or "",
            width=width or 0,
            height=height or 0,
            base_64_str=base_64_str,
            content_type=content_type,
        )
