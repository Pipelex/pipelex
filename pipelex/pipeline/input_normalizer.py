"""Normalize pipeline inputs by converting data URLs to pipelex-storage:// URIs.

This module provides functions to scan WorkingMemory and convert any ImageContent
with data URLs (data:...;base64,...) to pipelex-storage:// URIs for more efficient
pipeline processing.
"""

import base64
from typing import cast

import shortuuid

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.hub import get_storage_provider
from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.resolved_uri import ResolvedBase64DataUrl
from pipelex.tools.uri.uri_resolver import resolve_uri


def normalize_data_urls_to_storage(working_memory: WorkingMemory) -> WorkingMemory:
    """Convert all data URLs in ImageContent to pipelex-storage:// URIs.

    Scans all stuffs in working memory and for any ImageContent with a data:...;base64,...
    URL, stores the data and replaces the URL with a pipelex-storage:// URI.

    Args:
        working_memory: The working memory to normalize.

    Returns:
        The same WorkingMemory instance with normalized ImageContent URLs.
    """
    storage = get_storage_provider()

    for stuff in working_memory.root.values():
        content = stuff.content

        # Handle direct ImageContent
        if isinstance(content, ImageContent):
            normalized = _normalize_image_content(image_content=content, storage=storage)
            if normalized is not content:
                stuff.content = normalized

        # Handle ListContent of ImageContent
        elif isinstance(content, ListContent):
            # Check if the first item is an ImageContent to determine if this is a list of images
            raw_items = content.items  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            if raw_items and isinstance(raw_items[0], ImageContent):
                list_content = cast("ListContent[ImageContent]", content)
                image_items = list_content.items
                normalized_items: list[ImageContent] = []
                has_changes = False
                for image_item in image_items:
                    normalized_item = _normalize_image_content(image_content=image_item, storage=storage)
                    normalized_items.append(normalized_item)
                    if normalized_item is not image_item:
                        has_changes = True

                if has_changes:
                    stuff.content = ListContent[ImageContent](items=normalized_items)

    return working_memory


def _normalize_image_content(
    image_content: ImageContent,
    storage: StorageProviderAbstract,
) -> ImageContent:
    """Normalize a single ImageContent, converting data URLs to storage URIs.

    Args:
        image_content: The image content to normalize.
        storage: The storage provider to use.

    Returns:
        The original ImageContent if no normalization needed, or a new ImageContent
        with the normalized URL.
    """
    resolved_uri = resolve_uri(image_content.url)

    if not isinstance(resolved_uri, ResolvedBase64DataUrl):
        # Not a data URL, we can keep the original ImageContent without any changes
        return image_content

    # Decode base64 data and store
    raw_bytes = base64.b64decode(resolved_uri.base64_data)
    file_type = detect_file_type_from_bytes(raw_bytes)
    key = f"normalized/{shortuuid.uuid()}.{file_type.extension}"
    storage_uri = storage.store(data=raw_bytes, key=key)

    return ImageContent(
        url=storage_uri,
        display_link=image_content.display_link,
        mime_type=resolved_uri.mime_type or image_content.mime_type,
        source_prompt=image_content.source_prompt,
        source_negative_prompt=image_content.source_negative_prompt,
        caption=image_content.caption,
        size=image_content.size,
    )
