import base64
import hashlib

from pipelex.cogt.content_generation.exceptions import NeitherUrlNorDataError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails, GeneratedImageResolved
from pipelex.config import get_config
from pipelex.tools.misc.base_64_utils import (
    extract_base_64_str_from_base64_url_if_possible,
)
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx_async
from pipelex.tools.misc.image_utils import ImageFormat
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


class GeneratedContentFactory:
    def __init__(self, storage_provider: StorageProviderAbstract) -> None:
        self.storage_provider = storage_provider

    def _build_storage_key(
        self,
        primary_id: str,
        secondary_id: str,
        data: bytes,
        mime_type: str | None,
        output_format: ImageFormat | None,
    ) -> str:
        """Build a storage key using a SHA-256 hash of the data.

        Args:
            primary_id: The principal ID
            secondary_id: The secondary ID
            data: The binary data to hash
            mime_type: Optional MIME type to determine file extension
            output_format: Optional output format to determine file extension

        Returns:
            A storage key in the format "{primary_id}/{secondary_id}/{hash}.{extension}"
        """
        hash_digest = hashlib.sha256(data).hexdigest()[:16]

        if output_format:
            extension = output_format.as_file_extension
        elif mime_type:
            match mime_type:
                case "image/jpeg":
                    extension = "jpg"
                case "image/png":
                    extension = "png"
                case "image/webp":
                    extension = "webp"
                case _:
                    extension = "jpg"
        else:
            extension = "jpg"
        uri_format = get_config().pipelex.storage_config.uri_format
        return uri_format.format(primary_id=primary_id, secondary_id=secondary_id, hash=hash_digest, extension=extension)

    async def _fetch_remote_content(self, url: str) -> bytes:
        return await fetch_file_from_url_httpx_async(url=url)

    async def make_generated_image(
        self,
        primary_id: str,
        secondary_id: str,
        raw_details: GeneratedImageRawDetails,
    ) -> GeneratedImageResolved:
        output_format: ImageFormat | None = None
        base64_extracted_mime_type: str | None = None
        is_remote_url: bool
        if raw_details.output_format:
            output_format = ImageFormat(raw_details.output_format)

        if raw_details.actual_url:
            url = raw_details.actual_url
            is_remote_url = True
        else:
            actual_url: str | None = None
            actual_bytes: bytes | None = None
            if raw_details.base64_str:
                actual_bytes = base64.b64decode(raw_details.base64_str)
            elif raw_details.actual_url_or_prefixed_base64:
                if raw_details.actual_url_or_prefixed_base64.startswith("http"):
                    actual_url = raw_details.actual_url_or_prefixed_base64
                elif result := extract_base_64_str_from_base64_url_if_possible(possibly_base64_url=raw_details.actual_url_or_prefixed_base64):
                    base64_str, base64_extracted_mime_type = result
                    actual_bytes = base64.b64decode(base64_str)
                else:
                    msg = "No URL or base64 string could be extracted"
                    raise NeitherUrlNorDataError(msg)
            elif raw_details.actual_bytes:
                actual_bytes = raw_details.actual_bytes
            else:
                msg = "No URL or bytes or image found"
                raise NeitherUrlNorDataError(msg)

            if actual_url:
                url = actual_url
                is_remote_url = True
            elif actual_bytes:
                storage_key = self._build_storage_key(
                    primary_id=primary_id,
                    secondary_id=secondary_id,
                    data=actual_bytes,
                    mime_type=raw_details.mime_type or base64_extracted_mime_type,
                    output_format=output_format,
                )
                url = self.storage_provider.store(data=actual_bytes, key=storage_key)
                is_remote_url = False
            else:
                msg = "No URL or bytes found"
                raise NeitherUrlNorDataError(msg)

        mime_type: str | None = None
        if raw_details.mime_type:
            mime_type = raw_details.mime_type
        elif base64_extracted_mime_type:
            mime_type = base64_extracted_mime_type
        elif output_format:
            mime_type = output_format.as_mime_type
        else:
            mime_type = "image/jpeg"

        if is_remote_url and get_config().pipelex.storage_config.is_fetch_remote_content_enabled:
            actual_bytes = await self._fetch_remote_content(url=url)
            storage_key = self._build_storage_key(
                primary_id=primary_id,
                secondary_id=secondary_id,
                data=actual_bytes,
                mime_type=mime_type,
                output_format=output_format,
            )
            url = self.storage_provider.store(data=actual_bytes, key=storage_key)

        return GeneratedImageResolved(
            url=url,
            width=raw_details.width,
            height=raw_details.height,
            mime_type=mime_type,
        )
