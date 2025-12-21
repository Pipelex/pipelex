import base64
import hashlib

from pipelex import pretty_print
from pipelex.cogt.content_generation.exceptions import NeitherUrlNorDataError
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails, GeneratedImageResolved
from pipelex.cogt.img_gen.img_gen_job_components import OutputFormat
from pipelex.config import get_config
from pipelex.tools.misc.base_64_utils import (
    extract_base_64_str_from_base64_url_if_possible,
)
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx_async
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


class GeneratedContentFactory:
    def __init__(self, storage_provider: StorageProviderAbstract) -> None:
        self.storage_provider = storage_provider

    def _build_filename_from_hash(self, data: bytes, mime_type: str | None, output_format: OutputFormat | None) -> str:
        """Build a filename using a SHA-256 hash of the data.

        Args:
            data: The binary data to hash
            mime_type: Optional MIME type to determine file extension
            output_format: Optional output format to determine file extension
        Returns:
            A filename in the format "{hash}.{extension}"
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

        return f"{hash_digest}.{extension}"

    async def _fetch_remote_content(self, url: str) -> bytes:
        return await fetch_file_from_url_httpx_async(url=url)

    async def make_generated_image(
        self,
        raw_details: GeneratedImageRawDetails,
    ) -> GeneratedImageResolved:
        output_format: OutputFormat | None = None
        base64_extracted_mime_type: str | None = None
        is_remote_url: bool
        if raw_details.output_format:
            output_format = OutputFormat(raw_details.output_format)

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
                    msg = "No URL or base64 string found"
                    raise NeitherUrlNorDataError(msg)
            elif raw_details.actual_bytes:
                actual_bytes = raw_details.actual_bytes
            else:
                msg = "No URL or base64 string found"
                raise NeitherUrlNorDataError(msg)

            if actual_url:
                url = actual_url
                is_remote_url = True
            elif actual_bytes:
                storage_uri = self._build_filename_from_hash(
                    data=actual_bytes, mime_type=raw_details.mime_type or base64_extracted_mime_type, output_format=output_format
                )
                url = self.storage_provider.store(data=actual_bytes, uri=storage_uri)
                is_remote_url = False
            else:
                msg = "No URL or base64 string found"
                raise NeitherUrlNorDataError(msg)

        pretty_print(url, title="Generated image URL")

        mime_type: str | None = None
        if raw_details.mime_type:
            mime_type = raw_details.mime_type
        elif base64_extracted_mime_type:
            mime_type = base64_extracted_mime_type
        elif output_format:
            mime_type = output_format.as_mime_type
        else:
            mime_type = "image/jpeg"

        if is_remote_url and get_config().pipelex.storage_config.is_fetch_remote_content:
            actual_bytes = await self._fetch_remote_content(url=url)
            storage_uri = self._build_filename_from_hash(data=actual_bytes, mime_type=mime_type, output_format=output_format)
            url = self.storage_provider.store(data=actual_bytes, uri=storage_uri)

        return GeneratedImageResolved(
            url=url,
            width=raw_details.width,
            height=raw_details.height,
            mime_type=mime_type,
        )
