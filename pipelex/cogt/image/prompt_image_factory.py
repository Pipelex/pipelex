from typing import Optional

from pipelex.cogt.exceptions import PromptImageFactoryError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBytes, PromptImagePath, PromptImageUrl
from pipelex.tools.misc.base_64_utils import (
    encode_to_base64_async,
    load_binary_as_base64_async,
)
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx_async
from pipelex.tools.misc.path_utils import clarify_path_or_url


class PromptImageFactory:
    @classmethod
    def make_prompt_image(
        cls,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        base_64: Optional[bytes] = None,
    ) -> PromptImage:
        if file_path:
            return PromptImagePath(file_path=file_path)
        elif url:
            return PromptImageUrl(url=url)
        elif base_64:
            return PromptImageBytes(base_64=base_64)
        else:
            raise PromptImageFactoryError("PromptImageFactory requires one of file_path, url, or image_bytes")

    @classmethod
    def make_prompt_image_from_uri(
        cls,
        uri: str,
    ) -> PromptImage:
        file_path, url = clarify_path_or_url(path_or_uri=uri)
        return PromptImageFactory.make_prompt_image(
            file_path=file_path,
            url=url,
        )

    @classmethod
    async def make_promptimagebytes_from_url_async(
        cls,
        prompt_image_url: PromptImageUrl,
    ) -> PromptImageBytes:
        raw_image_bytes = await fetch_file_from_url_httpx_async(prompt_image_url.url)
        base_64 = await encode_to_base64_async(raw_image_bytes)
        return PromptImageBytes(base_64=base_64)

    @classmethod
    async def promptimage_to_b64_async(cls, image_prompt: PromptImage) -> bytes:
        if isinstance(image_prompt, PromptImagePath):
            return await load_binary_as_base64_async(image_prompt.file_path)
        elif isinstance(image_prompt, PromptImageBytes):
            return image_prompt.base_64
        elif isinstance(image_prompt, PromptImageUrl):
            image_bytes = await cls.make_promptimagebytes_from_url_async(image_prompt)
            return image_bytes.base_64
        else:
            raise PromptImageFactoryError(f"Unknown PromptImage type: {image_prompt}")
