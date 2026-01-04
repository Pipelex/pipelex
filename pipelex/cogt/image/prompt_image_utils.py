import asyncio
import base64

from pipelex.cogt.exceptions import PromptImageFactoryError
from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBase64,
    PromptImagePath,
    PromptImageTypedBase64,
    PromptImageTypedUrlOrBase64,
    PromptImageUrl,
)
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.hub import get_storage_provider
from pipelex.tools.misc.base64_utils import load_binary_as_base64_async
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import (
    detect_file_type_from_base64,
    detect_file_type_from_bytes,
)
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)
from pipelex.tools.uri.uri_resolver import resolve_uri


async def promptimage_to_b64_async(prompt_image: PromptImage) -> bytes:
    match prompt_image:
        case PromptImagePath():
            return await load_binary_as_base64_async(prompt_image.file_path)
        case PromptImageBase64():
            return prompt_image.base_64
        case PromptImageUrl():
            image_bytes = await PromptImageFactory.make_promptimagebase64_from_url_async(prompt_image)
            return image_bytes.base_64
        case _:
            msg = f"Unknown PromptImage type: {prompt_image}"
            raise PromptImageFactoryError(msg)


async def promptimage_to_bytes_async(prompt_image: PromptImage) -> bytes:
    match prompt_image:
        case PromptImagePath():
            return await load_binary_async(prompt_image.file_path)
        case PromptImageBase64():
            return prompt_image.get_decoded_bytes()
        case PromptImageUrl():
            image_bytes = await PromptImageFactory.make_promptimagebinary_from_url_async(prompt_image)
            return image_bytes.binary
        case _:
            msg = f"Unknown PromptImage type: {prompt_image}"
            raise PromptImageFactoryError(msg)


async def promptimage_to_typed_bytes_or_url(
    prompt_image: PromptImage,
    is_http_url_enabled: bool,
) -> PromptImageTypedUrlOrBase64:
    typed_bytes_or_url: PromptImageTypedUrlOrBase64
    if isinstance(prompt_image, PromptImageBase64):
        typed_bytes_or_url = prompt_image.make_prompt_image_typed_base64()
    elif isinstance(prompt_image, PromptImageUrl):
        resolved_uri = resolve_uri(prompt_image.url)
        match resolved_uri:
            case ResolvedPipelexStorage():
                storage_provider = get_storage_provider()
                image_bytes = storage_provider.load(uri=resolved_uri.storage_uri)
                file_type = detect_file_type_from_bytes(image_bytes)
                base64_bytes = base64.b64encode(image_bytes)
                typed_bytes_or_url = PromptImageTypedBase64(base_64=base64_bytes, file_type=file_type)
            case ResolvedHttpUrl():
                if is_http_url_enabled:
                    typed_bytes_or_url = resolved_uri.url
                else:
                    prompt_image_b64 = await PromptImageFactory.make_promptimagebase64_from_url_async(prompt_image_url=prompt_image)
                    file_type = detect_file_type_from_base64(prompt_image_b64.base_64)
                    typed_bytes_or_url = PromptImageTypedBase64(base_64=prompt_image_b64.base_64, file_type=file_type)
            case ResolvedLocalPath():
                prompt_image_path = PromptImagePath(file_path=resolved_uri.path)
                return await promptimage_to_typed_bytes_or_url(
                    prompt_image=prompt_image_path,
                    is_http_url_enabled=is_http_url_enabled,
                )
            case ResolvedBase64DataUrl():
                base64_bytes = resolved_uri.base64_data.encode("utf-8")
                file_type = detect_file_type_from_base64(base64_bytes)
                typed_bytes_or_url = PromptImageTypedBase64(base_64=base64_bytes, file_type=file_type)
    elif isinstance(prompt_image, PromptImagePath):
        b64 = await load_binary_as_base64_async(prompt_image.file_path)
        typed_bytes_or_url = PromptImageTypedBase64(base_64=b64, file_type=prompt_image.get_file_type())
    else:
        msg = f"Unsupported PromptImage type: '{type(prompt_image).__name__}'"
        raise PromptImageFactoryError(msg)
    return typed_bytes_or_url


async def prep_prompt_images(prompt_images: list[PromptImage], is_http_url_enabled: bool) -> list[PromptImageTypedUrlOrBase64]:
    tasks_to_prep_images = [promptimage_to_typed_bytes_or_url(prompt_image, is_http_url_enabled) for prompt_image in prompt_images]
    return await asyncio.gather(*tasks_to_prep_images)
