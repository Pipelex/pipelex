"""Utilities for preparing prompt images for LLM APIs.

This module provides functions to convert PromptImage instances into
PreparedImage instances that can be consumed by LLM provider APIs.
"""

import asyncio
import base64

from pipelex.cogt.image.prepared_image import PreparedImage, PreparedImageData, PreparedImageUrl
from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBase64,
    PromptImageBinary,
    PromptImageUri,
)
from pipelex.hub import get_storage_provider
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx_async
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64, detect_file_type_from_bytes
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)


async def prepare_prompt_image(
    prompt_image: PromptImage,
    is_http_url_enabled: bool,
) -> PreparedImage:
    """Prepare a single prompt image for LLM API consumption.

    Args:
        prompt_image: The input prompt image (URI, base64, or binary)
        is_http_url_enabled: Whether to pass HTTP URLs directly to the LLM

    Returns:
        A PreparedImage (URL or Data) ready for the LLM API
    """
    prepared: PreparedImage
    match prompt_image:
        case PromptImageBase64():
            prepared = PreparedImageData(
                base_64=prompt_image.base_64,
                file_type=prompt_image.get_file_type(),
            )

        case PromptImageBinary():
            base64_bytes = base64.b64encode(prompt_image.binary)
            prepared = PreparedImageData(
                base_64=base64_bytes,
                file_type=prompt_image.get_file_type(),
            )

        case PromptImageUri():
            match prompt_image.resolved:
                case ResolvedHttpUrl():
                    if is_http_url_enabled:
                        prepared = PreparedImageUrl(url=prompt_image.resolved.url)
                    else:
                        raw_bytes = await fetch_file_from_url_httpx_async(prompt_image.resolved.url)
                        prepared = PreparedImageData(
                            base_64=base64.b64encode(raw_bytes),
                            file_type=detect_file_type_from_bytes(raw_bytes),
                        )

                case ResolvedLocalPath():
                    raw_bytes = await load_binary_async(prompt_image.resolved.path)
                    prepared = PreparedImageData(
                        base_64=base64.b64encode(raw_bytes),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedPipelexStorage():
                    storage = get_storage_provider()
                    raw_bytes = storage.load(uri=prompt_image.resolved.storage_uri)
                    prepared = PreparedImageData(
                        base_64=base64.b64encode(raw_bytes),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedBase64DataUrl():
                    base64_bytes = prompt_image.resolved.base64_data.encode("utf-8")
                    prepared = PreparedImageData(
                        base_64=base64_bytes,
                        file_type=detect_file_type_from_base64(base64_bytes),
                    )

    return prepared


async def prep_prompt_images(
    prompt_images: list[PromptImage],
    is_http_url_enabled: bool,
) -> list[PreparedImage]:
    """Prepare multiple prompt images in parallel.

    Args:
        prompt_images: List of input prompt images
        is_http_url_enabled: Whether to pass HTTP URLs directly to the LLM

    Returns:
        List of PreparedImage instances ready for the LLM API
    """
    tasks = [prepare_prompt_image(prompt_image=img, is_http_url_enabled=is_http_url_enabled) for img in prompt_images]
    return list(await asyncio.gather(*tasks))
