import base64

from pydantic_core import Url
from typing_extensions import override

from pipelex.cogt.content_generation.exceptions import NeitherUrlNorDataError
from pipelex.cogt.content_generation.generated_content_factory_abstract import GeneratedContentFactoryAbstract
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails, GeneratedImageResolved
from pipelex.tools.misc.base_64_utils import is_prefixed_base64_url, prefixed_base64_str_from_base64_str


class GeneratedContentFactory(GeneratedContentFactoryAbstract):
    @override
    def make_generated_image(
        self,
        raw_details: GeneratedImageRawDetails,
    ) -> GeneratedImageResolved:
        url: str
        prefixed_base64_url: str | None = None
        if raw_details.actual_url:
            url = raw_details.actual_url
        else:
            if raw_details.base64_str:
                prefixed_base64_url = prefixed_base64_str_from_base64_str(b64_str=raw_details.base64_str)
            elif raw_details.actual_url_or_prefixed_base64:
                if is_prefixed_base64_url(possibly_base64_url=raw_details.actual_url_or_prefixed_base64):
                    prefixed_base64_url = raw_details.actual_url_or_prefixed_base64
                else:
                    prefixed_base64_url = prefixed_base64_str_from_base64_str(b64_str=raw_details.actual_url_or_prefixed_base64)
            elif raw_details.actual_bytes:
                base64_str = base64.b64encode(raw_details.actual_bytes).decode("utf-8")
                prefixed_base64_url = prefixed_base64_str_from_base64_str(base64_str)
            else:
                msg = "No URL or base64 string found"
                raise NeitherUrlNorDataError(msg)

            url = "RickRoll.jpg"

        return GeneratedImageResolved(
            url=url,
            prefixed_base64_url=prefixed_base64_url,
            width=raw_details.width,
            height=raw_details.height,
            content_type=raw_details.content_type,
        )
