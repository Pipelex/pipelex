from pipelex.cogt.exceptions import PromptImageFactoryError
from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBase64,
    PromptImageBinary,
    PromptImagePath,
    PromptImageTypedBase64,
    PromptImageTypedUrlOrBase64,
    PromptImageUrl,
)
from pipelex.tools.misc.base_64_utils import (
    encode_to_base64_async,
    load_binary_as_base64_async,
    load_binary_async,
    strip_base_64_str_if_needed,
)
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64


class PromptImageFactory:
    @classmethod
    def make_prompt_image(
        cls,
        file_path: str | None = None,
        url: str | None = None,
        base_64: bytes | None = None,
        base_64_str: str | None = None,
    ) -> PromptImage:
        if base_64:
            return PromptImageBase64(base_64=base_64)
        elif base_64_str:
            stripped_base_64_str = strip_base_64_str_if_needed(base_64_str)
            return PromptImageBase64(base_64=stripped_base_64_str.encode())
        elif file_path:
            return PromptImagePath(file_path=file_path)
        elif url:
            return PromptImageUrl(url=url)
        else:
            msg = "PromptImageFactory requires one of file_path, url, or image_bytes"
            raise PromptImageFactoryError(msg)

    @classmethod
    async def make_promptimagebase64_from_url_async(
        cls,
        prompt_image_url: PromptImageUrl,
    ) -> PromptImageBase64:
        raw_image_bytes = await fetch_file_from_url_httpx_async(prompt_image_url.url)
        base_64 = await encode_to_base64_async(raw_image_bytes)
        return PromptImageBase64(base_64=base_64)

    @classmethod
    async def make_promptimagebinary_from_url_async(
        cls,
        prompt_image_url: PromptImageUrl,
    ) -> PromptImageBinary:
        raw_image_bytes = await fetch_file_from_url_httpx_async(prompt_image_url.url)
        return PromptImageBinary(binary=raw_image_bytes)
