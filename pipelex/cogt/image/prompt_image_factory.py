from pipelex.cogt.exceptions import PromptImageFactoryError
from pipelex.cogt.image.prompt_image import PromptImage, PromptImageBase64, PromptImageBinary, PromptImagePath, PromptImageUrl
from pipelex.tools.misc.base_64_utils import (
    encode_to_base64_async,
    load_binary_as_base64_async,
    load_binary_async,
)
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx_async
from pipelex.tools.misc.path_utils import clarify_path_or_url


class PromptImageFactory:
    @classmethod
    def make_prompt_image(
        cls,
        file_path: str | None = None,
        url: str | None = None,
        base_64: bytes | None = None,
    ) -> PromptImage:
        if file_path:
            return PromptImagePath(file_path=file_path)
        elif url:
            return PromptImageUrl(url=url)
        elif base_64:
            return PromptImageBase64(base_64=base_64)
        else:
            msg = "PromptImageFactory requires one of file_path, url, or image_bytes"
            raise PromptImageFactoryError(msg)

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

    @classmethod
    async def promptimage_to_b64_async(cls, prompt_image: PromptImage) -> bytes:
        match prompt_image:
            case PromptImagePath():
                return await load_binary_as_base64_async(prompt_image.file_path)
            case PromptImageBase64():
                return prompt_image.base_64
            case PromptImageUrl():
                image_bytes = await cls.make_promptimagebase64_from_url_async(prompt_image)
                return image_bytes.base_64
            case _:
                msg = f"Unknown PromptImage type: {prompt_image}"
                raise PromptImageFactoryError(msg)

    @classmethod
    async def promptimage_to_bytes_async(cls, prompt_image: PromptImage) -> bytes:
        match prompt_image:
            case PromptImagePath():
                return await load_binary_async(prompt_image.file_path)
            case PromptImageBase64():
                return prompt_image.get_decoded_bytes()
            case PromptImageUrl():
                image_bytes = await cls.make_promptimagebinary_from_url_async(prompt_image)
                return image_bytes.binary
            case _:
                msg = f"Unknown PromptImage type: {prompt_image}"
                raise PromptImageFactoryError(msg)
