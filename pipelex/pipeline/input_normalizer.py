"""Normalize pipeline inputs by converting data URLs to pipelex-storage:// URIs.

This module provides functions to scan WorkingMemory and convert any ImageContent
with data URLs (data:...;base64,...) to pipelex-storage:// URIs for more efficient
pipeline processing.
"""

import base64
from typing import Any, cast

import shortuuid

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.hub import get_storage_provider
from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.resolved_uri import ResolvedBase64DataUrl
from pipelex.tools.uri.uri_resolver import resolve_uri


def normalize_data_urls_to_storage(working_memory: WorkingMemory) -> WorkingMemory:
    """Convert all data URLs in ImageContent to pipelex-storage:// URIs.

    Scans all stuffs in working memory and for any ImageContent with a data:...;base64,...
    URL, stores the data and replaces the URL with a pipelex-storage:// URI.

    This handles:
    - Direct ImageContent
    - ListContent containing ImageContent items
    - StructuredContent with nested ImageContent fields (recursive)

    Args:
        working_memory: The working memory to normalize.

    Returns:
        The same WorkingMemory instance with normalized ImageContent URLs.
    """
    storage = get_storage_provider()

    for stuff in working_memory.root.values():
        content = stuff.content
        normalized_content, changed = _normalize_value(value=content, storage=storage)
        if changed:
            stuff.content = normalized_content

    return working_memory


def _normalize_value(
    value: Any,
    storage: StorageProviderAbstract,
) -> tuple[Any, bool]:
    """Recursively normalize a value, converting data URLs in ImageContent to storage URIs.

    Args:
        value: The value to normalize (can be ImageContent, StructuredContent, list, or any other type).
        storage: The storage provider to use.

    Returns:
        A tuple of (normalized_value, has_changed).
    """
    # Handle ImageContent directly
    if isinstance(value, ImageContent):
        normalized = _normalize_image_content(image_content=value, storage=storage)
        return normalized, normalized is not value

    # Handle StructuredContent (recursively process all fields)
    if isinstance(value, StructuredContent):
        return _normalize_structured_content(structured_content=value, storage=storage)

    # Handle ListContent
    if isinstance(value, ListContent):
        return _normalize_list_content(list_content=value, storage=storage)  # pyright: ignore[reportUnknownArgumentType]

    # Handle plain lists (might contain ImageContent or StructuredContent)
    if isinstance(value, list):
        return _normalize_list(items=value, storage=storage)  # pyright: ignore[reportUnknownArgumentType]

    # Other types don't need normalization
    return value, False


def _normalize_structured_content(
    structured_content: StructuredContent,
    storage: StorageProviderAbstract,
) -> tuple[StructuredContent, bool]:
    """Normalize a StructuredContent by recursively processing all its fields.

    Args:
        structured_content: The structured content to normalize.
        storage: The storage provider to use.

    Returns:
        A tuple of (normalized_content, has_changed).
    """
    updates: dict[str, Any] = {}
    has_changes = False

    for field_name, field_value in structured_content:
        normalized_value, changed = _normalize_value(value=field_value, storage=storage)
        if changed:
            updates[field_name] = normalized_value
            has_changes = True

    if not has_changes:
        return structured_content, False

    # Create a new instance with updated fields
    # Use model_copy with update to preserve all other fields
    return structured_content.model_copy(update=updates), True


def _normalize_list_content(
    list_content: ListContent[Any],
    storage: StorageProviderAbstract,
) -> tuple[ListContent[Any], bool]:
    """Normalize a ListContent by processing all its items.

    Args:
        list_content: The list content to normalize.
        storage: The storage provider to use.

    Returns:
        A tuple of (normalized_list_content, has_changed).
    """
    raw_items = list_content.items  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    if not raw_items:
        return list_content, False

    normalized_items, has_changes = _normalize_list(items=raw_items, storage=storage)  # pyright: ignore[reportUnknownArgumentType]

    if not has_changes:
        return list_content, False

    # Check the type of the first item to determine the ListContent type
    first_item = normalized_items[0]
    if isinstance(first_item, ImageContent):
        return ListContent[ImageContent](items=cast("list[ImageContent]", normalized_items)), True

    # For other types (e.g., StructuredContent subclasses), use generic ListContent
    return ListContent(items=normalized_items), True


def _normalize_list(
    items: list[Any],
    storage: StorageProviderAbstract,
) -> tuple[list[Any], bool]:
    """Normalize a list by processing all its items.

    Args:
        items: The list items to normalize.
        storage: The storage provider to use.

    Returns:
        A tuple of (normalized_items, has_changed).
    """
    normalized_items: list[Any] = []
    has_changes = False

    for item in items:
        normalized_item, changed = _normalize_value(value=item, storage=storage)
        normalized_items.append(normalized_item)
        if changed:
            has_changes = True

    return normalized_items, has_changes


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
