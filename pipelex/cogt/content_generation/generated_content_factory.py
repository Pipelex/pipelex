import base64
import hashlib

from pipelex.cogt.content_generation.exceptions import NeitherUrlNorDataError
from pipelex.cogt.extract.extract_output import ExtractOutput
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.config import get_config
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.misc.base64_utils import extract_base64_str_from_base64_url_if_possible
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
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
        image_format: ImageFormat | None,
    ) -> str:
        """Build a storage key using a SHA-256 hash of the data.

        Args:
            primary_id: The principal ID
            secondary_id: The secondary ID
            data: The binary data to hash
            mime_type: Optional MIME type to determine file extension
            image_format: Optional output format to determine file extension

        Returns:
            A storage key in the format "{primary_id}/{secondary_id}/{hash}.{extension}"
        """
        hash_digest = hashlib.sha256(data).hexdigest()[:16]

        if image_format:
            extension = image_format.as_file_extension
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
        return await fetch_file_from_url_httpx(url=url)

    async def make_image_content(
        self,
        primary_id: str,
        secondary_id: str,
        raw_details: GeneratedImageRawDetails,
    ) -> ImageContent:
        image_format: ImageFormat | None = None
        base64_extracted_mime_type: str | None = None
        is_remote_url: bool
        if raw_details.image_format:
            image_format = ImageFormat(raw_details.image_format)

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
                elif result := extract_base64_str_from_base64_url_if_possible(possibly_base64_url=raw_details.actual_url_or_prefixed_base64):
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
                    image_format=image_format,
                )
                url = await self.storage_provider.store(data=actual_bytes, key=storage_key)
                is_remote_url = False
            else:
                msg = "No URL or bytes found"
                raise NeitherUrlNorDataError(msg)

        mime_type: str | None = None
        if raw_details.mime_type:
            mime_type = raw_details.mime_type
        elif base64_extracted_mime_type:
            mime_type = base64_extracted_mime_type
        elif image_format:
            mime_type = image_format.as_mime_type
        else:
            mime_type = "image/jpeg"

        display_link: str | None
        if is_remote_url and get_config().pipelex.storage_config.is_fetch_remote_content_enabled:
            actual_bytes = await self._fetch_remote_content(url=url)
            storage_key = self._build_storage_key(
                primary_id=primary_id,
                secondary_id=secondary_id,
                data=actual_bytes,
                mime_type=mime_type,
                image_format=image_format,
            )
            url = await self.storage_provider.store(data=actual_bytes, key=storage_key)
            display_link = await self.storage_provider.display_link(uri=url)
        elif not is_remote_url:
            display_link = await self.storage_provider.display_link(uri=url)
        else:
            display_link = url

        return ImageContent(
            url=url,
            display_link=display_link,
            size=raw_details.size,
            mime_type=mime_type,
            caption=raw_details.caption,
        )

    async def make_page_contents(
        self,
        primary_id: str,
        secondary_id: str,
        extract_output: ExtractOutput,
    ) -> list[PageContent]:
        page_contents: list[PageContent] = []
        for page_index in sorted(extract_output.pages.keys()):
            page = extract_output.pages[page_index]
            page_images: list[ImageContent] = []
            for extracted_image in page.extracted_images:
                image_content = await self.make_image_content(
                    primary_id=primary_id,
                    secondary_id=secondary_id,
                    raw_details=extracted_image,
                )
                page_images.append(image_content)
            page_contents.append(
                PageContent(
                    text_and_images=TextAndImagesContent(
                        text=TextContent(text=page.text) if page.text else None,
                        images=page_images,
                    ),
                )
            )
        return page_contents
