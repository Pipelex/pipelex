import base64
import hashlib

from typing_extensions import override

from pipelex import pretty_print
from pipelex.cogt.content_generation.exceptions import NeitherUrlNorDataError
from pipelex.cogt.content_generation.generated_content_factory_abstract import GeneratedContentFactoryAbstract
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails, GeneratedImageResolved
from pipelex.tools.misc.base_64_utils import (
    extract_base_64_str_from_base64_url_if_possible,
)
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


class GeneratedContentFactory(GeneratedContentFactoryAbstract):
    def __init__(self, storage_provider: StorageProviderAbstract) -> None:
        self.storage_provider = storage_provider

    def _build_filename_from_hash(self, data: bytes, content_type: str | None) -> str:
        """Build a filename using a SHA-256 hash of the data.

        Args:
            data: The binary data to hash
            content_type: Optional MIME type to determine file extension

        Returns:
            A filename in the format "{hash}.{extension}"
        """
        hash_digest = hashlib.sha256(data).hexdigest()[:16]

        extension = "jpg"
        if content_type:
            extension_map = {
                "image/jpeg": "jpg",
                "image/png": "png",
                "image/gif": "gif",
                "image/webp": "webp",
            }
            extension = extension_map.get(content_type, "jpg")

        return f"{hash_digest}.{extension}"

    @override
    def make_generated_image(
        self,
        raw_details: GeneratedImageRawDetails,
    ) -> GeneratedImageResolved:
        if raw_details.actual_url:
            url = raw_details.actual_url
        else:
            actual_url: str | None = None
            actual_bytes: bytes | None = None
            if raw_details.base64_str:
                actual_bytes = base64.b64decode(raw_details.base64_str)
            elif raw_details.actual_url_or_prefixed_base64:
                if raw_details.actual_url_or_prefixed_base64.startswith("http"):
                    actual_url = raw_details.actual_url_or_prefixed_base64
                elif base64_str := extract_base_64_str_from_base64_url_if_possible(possibly_base64_url=raw_details.actual_url_or_prefixed_base64):
                    actual_bytes = base64.b64decode(base64_str)
                else:
                    msg = "No URL or base64 string found"
                    raise NeitherUrlNorDataError(msg)
            elif raw_details.actual_bytes:
                actual_bytes = raw_details.actual_bytes
            else:
                msg = "No URL or base64 string found"
                raise NeitherUrlNorDataError(msg)

            if actual_url:
                url = actual_url
            elif actual_bytes:
                filename = self._build_filename_from_hash(data=actual_bytes, content_type=raw_details.content_type)
                url = self.storage_provider.store(data=actual_bytes, uri=filename)
            else:
                msg = "No URL or base64 string found"
                raise NeitherUrlNorDataError(msg)

        pretty_print(url, title="Generated image URL")

        return GeneratedImageResolved(
            url=url,
            width=raw_details.width,
            height=raw_details.height,
            content_type=raw_details.content_type,
        )
