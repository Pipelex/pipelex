"""Utilities for preparing prompt images for LLM APIs.

This module provides functions to convert PromptImage instances into
PreparedFile instances that can be consumed by LLM provider APIs.
"""

import base64
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from pipelex.cogt.image.prompt_image import (
    PromptImage,
    PromptImageBase64,
    PromptImageBinary,
    PromptImageUri,
)
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.misc.async_utils import gather_bounded
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx, fetching_for_input
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64, detect_file_type_from_bytes
from pipelex.tools.uri.prepared_file import PreparedFile, PreparedFileBase64, PreparedFileHttpUrl
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)
from pipelex.tools.uri.uri_bytes import MAX_CONCURRENT_URI_READS

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable


async def prepare_prompt_image(
    prompt_image: PromptImage,
    *,
    is_http_url_enabled: bool,
) -> PreparedFile:
    """Prepare a single prompt image for LLM API consumption.

    Args:
        prompt_image: The input prompt image (URI, base64, or binary)
        is_http_url_enabled: Whether to pass HTTP URLs directly to the LLM

    Returns:
        A PreparedFile (HttpUrl or Base64) ready for the LLM API
    """
    prepared: PreparedFile
    match prompt_image:
        case PromptImageBase64():
            prepared = PreparedFileBase64(
                base64_data=prompt_image.base64_data,
                file_type=prompt_image.get_file_type(),
            )

        case PromptImageBinary():
            base64_data = base64.b64encode(prompt_image.raw_bytes).decode("ascii")
            prepared = PreparedFileBase64(
                base64_data=base64_data,
                file_type=prompt_image.get_file_type(),
            )

        case PromptImageUri():
            match prompt_image.resolved:
                case ResolvedHttpUrl() as resolved_uri:
                    if is_http_url_enabled:
                        prepared = PreparedFileHttpUrl(url=resolved_uri.url)
                    else:
                        with fetching_for_input(input_name=prompt_image.input_name):
                            raw_bytes = await fetch_file_from_url_httpx(url=resolved_uri.url)
                        prepared = PreparedFileBase64(
                            base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                            file_type=detect_file_type_from_bytes(raw_bytes),
                        )

                case ResolvedLocalPath() as resolved_uri:
                    raw_bytes = await load_binary_async(Path(resolved_uri.path))
                    prepared = PreparedFileBase64(
                        base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedPipelexStorage() as resolved_uri:
                    storage = get_storage_provider()
                    raw_bytes = await storage.load(uri=resolved_uri.storage_uri)
                    prepared = PreparedFileBase64(
                        base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedBase64DataUrl() as resolved_uri:
                    # base64_data from ResolvedBase64DataUrl is already a string
                    base64_data = resolved_uri.base64_data
                    prepared = PreparedFileBase64(
                        base64_data=base64_data,
                        file_type=detect_file_type_from_base64(base64_data),
                    )

    return prepared


async def prep_prompt_images(
    prompt_images: list[PromptImage],
    *,
    is_http_url_enabled: bool,
) -> list[PreparedFile]:
    """Prepare multiple prompt images in parallel.

    Args:
        prompt_images: List of input prompt images
        is_http_url_enabled: Whether to pass HTTP URLs directly to the LLM

    Returns:
        List of PreparedFile instances ready for the LLM API
    """
    # A bounded number at a time, so a prompt holding many images does not open as many reads at once.
    prepare_factories: list[Callable[[], Awaitable[PreparedFile]]] = [
        partial(prepare_prompt_image, prompt_image=prompt_image, is_http_url_enabled=is_http_url_enabled) for prompt_image in prompt_images
    ]
    return await gather_bounded(prepare_factories, max_concurrency=MAX_CONCURRENT_URI_READS)


async def prepare_prompt_image_as_base64(prompt_image: PromptImage) -> PreparedFileBase64:
    """Prepare a prompt image, always returning base64-encoded data.

    This variant always fetches HTTP URLs and converts everything to base64.
    Use this when the LLM API doesn't support HTTP URLs directly.

    Args:
        prompt_image: The input prompt image (URI, base64, or binary)

    Returns:
        A PreparedFileBase64 ready for the LLM API
    """
    match prompt_image:
        case PromptImageBase64():
            return PreparedFileBase64(
                base64_data=prompt_image.base64_data,
                file_type=prompt_image.get_file_type(),
            )

        case PromptImageBinary():
            base64_data = base64.b64encode(prompt_image.raw_bytes).decode("ascii")
            return PreparedFileBase64(
                base64_data=base64_data,
                file_type=prompt_image.get_file_type(),
            )

        case PromptImageUri():
            match prompt_image.resolved:
                case ResolvedHttpUrl() as resolved_uri:
                    with fetching_for_input(input_name=prompt_image.input_name):
                        raw_bytes = await fetch_file_from_url_httpx(url=resolved_uri.url)
                    return PreparedFileBase64(
                        base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedLocalPath() as resolved_uri:
                    raw_bytes = await load_binary_async(Path(resolved_uri.path))
                    return PreparedFileBase64(
                        base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedPipelexStorage() as resolved_uri:
                    storage = get_storage_provider()
                    raw_bytes = await storage.load(uri=resolved_uri.storage_uri)
                    return PreparedFileBase64(
                        base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                        file_type=detect_file_type_from_bytes(raw_bytes),
                    )

                case ResolvedBase64DataUrl() as resolved_uri:
                    base64_data = resolved_uri.base64_data
                    return PreparedFileBase64(
                        base64_data=base64_data,
                        file_type=detect_file_type_from_base64(base64_data),
                    )
