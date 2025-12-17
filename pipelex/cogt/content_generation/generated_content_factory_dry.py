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
            prefixed_base64_url=raw_details.actual_url_or_prefixed_base64 or "",
            content_type=raw_details.content_type or "",
            width=raw_details.width,
            height=raw_details.height,
        )
