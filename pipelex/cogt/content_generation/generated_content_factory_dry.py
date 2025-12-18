from typing_extensions import override

from pipelex.cogt.content_generation.generated_content_factory_abstract import GeneratedContentFactoryAbstract
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails, GeneratedImageResolved


class GeneratedContentFactoryDry(GeneratedContentFactoryAbstract):
    @override
    def make_generated_image(
        self,
        raw_details: GeneratedImageRawDetails,
    ) -> GeneratedImageResolved:
        return GeneratedImageResolved(
            url=raw_details.actual_url or "",
            mime_type=raw_details.mime_type or "",
            width=raw_details.width,
            height=raw_details.height,
        )
