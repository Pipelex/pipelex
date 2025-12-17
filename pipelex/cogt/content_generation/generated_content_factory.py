import base64

from typing_extensions import override

from pipelex import pretty_print
from pipelex.cogt.content_generation.exceptions import NeitherUrlNorDataError
from pipelex.cogt.content_generation.generated_content_factory_abstract import GeneratedContentFactoryAbstract
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails, GeneratedImageResolved
from pipelex.tools.misc.base_64_utils import is_prefixed_base64_url, prefixed_base64_str_from_base64_str, strip_base_64_str_if_needed
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


class GeneratedContentFactory(GeneratedContentFactoryAbstract):
    def __init__(self, storage_provider: StorageProviderAbstract) -> None:
        self.storage_provider = storage_provider

    @override
    def make_generated_image(
        self,
        raw_details: GeneratedImageRawDetails,
    ) -> GeneratedImageResolved:
        pretty_print(raw_details, title="Raw details")
        the_url: str | None = None
        the_prefixed_base64_url: str | None = None
        if raw_details.actual_url:
            url = raw_details.actual_url
        else:
            actual_bytes: bytes | None = None
            if raw_details.base64_str:
                the_prefixed_base64_url = prefixed_base64_str_from_base64_str(b64_str=raw_details.base64_str)
                actual_bytes = base64.b64decode(raw_details.base64_str)
            elif raw_details.actual_url_or_prefixed_base64:
                if is_prefixed_base64_url(possibly_base64_url=raw_details.actual_url_or_prefixed_base64):
                    the_prefixed_base64_url = raw_details.actual_url_or_prefixed_base64
                    base64_str = strip_base_64_str_if_needed(base64_str=the_prefixed_base64_url)
                    actual_bytes = base64.b64decode(base64_str)
                else:
                    the_url = raw_details.actual_url_or_prefixed_base64
            elif raw_details.actual_bytes:
                # base64_str = base64.b64encode(raw_details.actual_bytes).decode("utf-8")
                # prefixed_base64_url = prefixed_base64_str_from_base64_str(base64_str)
                actual_bytes = raw_details.actual_bytes
            else:
                msg = "No URL or base64 string found"
                raise NeitherUrlNorDataError(msg)

            if the_url:
                url = the_url
            elif actual_bytes:
                url = self.storage_provider.store(data=actual_bytes, uri="test_01.jpg")
            else:
                msg = "No URL or base64 string found"
                raise NeitherUrlNorDataError(msg)

        pretty_print(url, title="Generated image URL")

        return GeneratedImageResolved(
            url=url,
            prefixed_base64_url=the_prefixed_base64_url,
            width=raw_details.width,
            height=raw_details.height,
            content_type=raw_details.content_type,
        )
