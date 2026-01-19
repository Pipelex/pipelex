"""Normalize pipeline inputs by converting data URLs to pipelex-storage:// URIs.

This module provides functions to scan WorkingMemory and convert any ImageContent
or DocumentContent with data URLs (data:...;base64,...) to pipelex-storage:// URIs
for more efficient pipeline processing.
"""

import base64
from typing import Any, cast

import shortuuid

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.hub import get_storage_provider
from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.resolved_uri import ResolvedBase64DataUrl
from pipelex.tools.uri.uri_resolver import resolve_uri

# Type alias for content types that can have their URLs normalized
NormalizableContent = ImageContent | DocumentContent


async def normalize_data_urls_to_storage(working_memory: WorkingMemory) -> WorkingMemory:
    """Convert all data URLs in ImageContent and DocumentContent to pipelex-storage:// URIs.

    Scans all stuffs in working memory and for any ImageContent or DocumentContent with
    a data:...;base64,... URL, stores the data and replaces the URL with a pipelex-storage:// URI.

    This handles:

    - Direct ImageContent and DocumentContent
    - ListContent containing ImageContent or DocumentContent items
    - StructuredContent with nested ImageContent or DocumentContent fields (recursive)

    Args:
        working_memory: The working memory to normalize.

    Returns:
        The same WorkingMemory instance with normalized URLs.
    """
    storage = get_storage_provider()

    for stuff in working_memory.root.values():
        content = stuff.content
        normalized_content, changed = await _normalize_value(value=content, storage=storage)
        if changed:
            stuff.content = normalized_content

    return working_memory


async def _normalize_value(
    value: Any,
    storage: StorageProviderAbstract,
) -> tuple[Any, bool]:
    """Recursively normalize a value, converting data URLs in ImageContent/DocumentContent to storage URIs.

    Args:
        value: The value to normalize (can be ImageContent, DocumentContent, StructuredContent, list, or any other type).
        storage: The storage provider to use.

    Returns:
        A tuple of (normalized_value, has_changed).
    """
    # Handle ImageContent and DocumentContent
    if isinstance(value, (ImageContent, DocumentContent)):
        normalized = await _normalize_url_content(content=value, storage=storage)
        return normalized, normalized is not value

    # Handle StructuredContent (recursively process all fields)
    if isinstance(value, StructuredContent):
        return await _normalize_structured_content(structured_content=value, storage=storage)

    # Handle ListContent
    if isinstance(value, ListContent):
        return await _normalize_list_content(list_content=value, storage=storage)  # pyright: ignore[reportUnknownArgumentType]

    # Handle plain lists (might contain ImageContent, DocumentContent, or StructuredContent)
    if isinstance(value, list):
        return await _normalize_list(items=value, storage=storage)  # pyright: ignore[reportUnknownArgumentType]

    # Other types don't need normalization
    return value, False


async def _normalize_structured_content(
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
        normalized_value, changed = await _normalize_value(value=field_value, storage=storage)
        if changed:
            updates[field_name] = normalized_value
            has_changes = True

    if not has_changes:
        return structured_content, False

    # Create a new instance with updated fields
    # Use model_copy with update to preserve all other fields
    return structured_content.model_copy(update=updates), True


async def _normalize_list_content(
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

    normalized_items, has_changes = await _normalize_list(items=raw_items, storage=storage)  # pyright: ignore[reportUnknownArgumentType]

    if not has_changes:
        return list_content, False

    # Check the type of the first item to determine the ListContent type
    first_item = normalized_items[0]
    if isinstance(first_item, ImageContent):
        return ListContent[ImageContent](items=cast("list[ImageContent]", normalized_items)), True
    if isinstance(first_item, DocumentContent):
        return ListContent[DocumentContent](items=cast("list[DocumentContent]", normalized_items)), True

    # For other types (e.g., StructuredContent subclasses), use generic ListContent
    return ListContent(items=normalized_items), True


async def _normalize_list(
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
        normalized_item, changed = await _normalize_value(value=item, storage=storage)
        normalized_items.append(normalized_item)
        if changed:
            has_changes = True

    return normalized_items, has_changes


async def _normalize_url_content(
    content: NormalizableContent,
    storage: StorageProviderAbstract,
) -> NormalizableContent:
    """Normalize ImageContent or DocumentContent by converting data URLs to storage URIs.

    Args:
        content: The image or document content to normalize.
        storage: The storage provider to use.

    Returns:
        The original content if no normalization needed, or a new instance
        with the normalized URL.
    """
    resolved_uri = resolve_uri(content.url)

    if not isinstance(resolved_uri, ResolvedBase64DataUrl):
        # Not a data URL, we can keep the original content without any changes
        return content

    # Decode base64 data and store
    raw_bytes = base64.b64decode(resolved_uri.base64_data)
    file_type = detect_file_type_from_bytes(raw_bytes)
    key = f"normalized/{shortuuid.uuid()}.{file_type.extension}"
    storage_uri = await storage.store(data=raw_bytes, key=key)

    # Use model_copy to preserve all type-specific fields
    return content.model_copy(
        update={
            "url": storage_uri,
            "mime_type": resolved_uri.mime_type or content.mime_type,
        }
    )
