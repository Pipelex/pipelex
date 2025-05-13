# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pipelex.cogt.exceptions import PromptImageFactoryError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBytes, PromptImagePath, PromptImageUrl
from pipelex.tools.misc.file_fetching_helpers import fetch_file_from_url_httpx_async
from pipelex.tools.utils.image_utils import (
    load_image_as_base64_from_bytes_async,
    load_image_as_base64_from_path_async,
)


class PromptImageFactory:
    @staticmethod
    def make_prompt_image(
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        image_bytes: Optional[bytes] = None,
    ) -> PromptImage:
        if file_path:
            return PromptImagePath(file_path=file_path)
        elif url:
            return PromptImageUrl(url=url)
        elif image_bytes:
            return PromptImageBytes(b64_image_bytes=image_bytes)
        else:
            raise PromptImageFactoryError("PromptImageFactory requires one of file_path, url, or image_bytes")

    @classmethod
    async def make_promptimagebytes_from_url_async(
        cls,
        prompt_image_url: PromptImageUrl,
    ) -> PromptImageBytes:
        raw_image_bytes = await fetch_file_from_url_httpx_async(prompt_image_url.url)
        b64_image_bytes = await load_image_as_base64_from_bytes_async(raw_image_bytes)
        return PromptImageBytes(b64_image_bytes=b64_image_bytes)

    @classmethod
    async def promptimage_to_b64_async(cls, image_prompt: PromptImage) -> bytes:
        if isinstance(image_prompt, PromptImagePath):
            return await load_image_as_base64_from_path_async(image_prompt.file_path)
        elif isinstance(image_prompt, PromptImageBytes):
            return image_prompt.b64_image_bytes
        elif isinstance(image_prompt, PromptImageUrl):
            image_bytes = await cls.make_promptimagebytes_from_url_async(image_prompt)
            return image_bytes.b64_image_bytes
        else:
            raise PromptImageFactoryError(f"Unknown PromptImage type: {image_prompt}")
