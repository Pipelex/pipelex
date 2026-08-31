"""Normalize pipeline inputs by converting data URLs and local file paths to pipelex-storage:// URIs.

This module provides functions to scan WorkingMemory and convert any ImageContent
or DocumentContent with data URLs (data:...;base64,...) or local file paths to
pipelex-storage:// URIs for more efficient pipeline processing.
"""

import base64
from pathlib import Path
from typing import Any, cast

import shortuuid

from pipelex.config import get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipeline.exceptions import PipelineInputContentError, PipelineInputUrlMissingError
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_bytes
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.resolved_uri import ResolvedBase64DataUrl, ResolvedLocalPath
from pipelex.tools.uri.uri_resolver import resolve_uri

# Type alias for content types that can have their URLs normalized
NormalizableContent = ImageContent | DocumentContent


async def normalize_data_urls_to_storage(working_memory: WorkingMemory, *, storage_scope: str) -> WorkingMemory:
    """Convert all data URLs in ImageContent and DocumentContent to pipelex-storage:// URIs.

    Scans all stuffs in working memory and for any ImageContent or DocumentContent with
    a data:...;base64,... URL, stores the data and replaces the URL with a pipelex-storage:// URI.

    This handles:

    - Direct ImageContent and DocumentContent
    - ListContent containing ImageContent or DocumentContent items
    - StructuredContent with nested ImageContent or DocumentContent fields (recursive)

    Args:
        working_memory: The working memory to normalize.
        storage_scope: The run's opaque storage prefix. Normalized bytes land
            under `{storage_scope}/assets/`, inside the run's own namespace —
            they used to go to a flat top-level `normalized/` prefix shared by
            every run of every tenant.

    Returns:
        The same WorkingMemory instance with normalized URLs.
    """
    storage = get_storage_provider()

    for stuff in working_memory.root.values():
        content = stuff.content
        normalized_content, changed = await _normalize_value(value=content, storage=storage, storage_scope=storage_scope)
        if changed:
            stuff.content = normalized_content

    return working_memory


async def _normalize_value(
    value: Any,
    *,
    storage: StorageProviderAbstract,
    storage_scope: str,
) -> tuple[Any, bool]:
    """Recursively normalize a value, converting data URLs in ImageContent/DocumentContent to storage URIs.

    Args:
        value: The value to normalize (can be ImageContent, DocumentContent, StructuredContent, list, or any other type).
        storage: The storage provider to use.
        storage_scope: The run's opaque storage prefix; normalized bytes land
            under `{storage_scope}/assets/`.

    Returns:
        A tuple of (normalized_value, has_changed).
    """
    # Handle ImageContent and DocumentContent
    if isinstance(value, (ImageContent, DocumentContent)):
        normalized = await _normalize_url_content(content=value, storage=storage, storage_scope=storage_scope)
        return normalized, normalized is not value

    # Handle StructuredContent (recursively process all fields)
    if isinstance(value, StructuredContent):
        return await _normalize_structured_content(structured_content=value, storage=storage, storage_scope=storage_scope)

    # Handle ListContent
    if isinstance(value, ListContent):
        return await _normalize_list_content(list_content=value, storage=storage, storage_scope=storage_scope)  # pyright: ignore[reportUnknownArgumentType]

    # Handle plain lists (might contain ImageContent, DocumentContent, or StructuredContent)
    if isinstance(value, list):
        return await _normalize_list(items=value, storage=storage, storage_scope=storage_scope)  # pyright: ignore[reportUnknownArgumentType]

    # Other types don't need normalization
    return value, False


async def _normalize_structured_content(
    structured_content: StructuredContent,
    *,
    storage: StorageProviderAbstract,
    storage_scope: str,
) -> tuple[StructuredContent, bool]:
    """Normalize a StructuredContent by recursively processing all its fields.

    Args:
        structured_content: The structured content to normalize.
        storage: The storage provider to use.
        storage_scope: The run's opaque storage prefix; normalized bytes land
            under `{storage_scope}/assets/`.

    Returns:
        A tuple of (normalized_content, has_changed).
    """
    updates: dict[str, Any] = {}
    has_changes = False

    for field_name, field_value in structured_content:
        normalized_value, changed = await _normalize_value(value=field_value, storage=storage, storage_scope=storage_scope)
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
    *,
    storage: StorageProviderAbstract,
    storage_scope: str,
) -> tuple[ListContent[Any], bool]:
    """Normalize a ListContent by processing all its items.

    Args:
        list_content: The list content to normalize.
        storage: The storage provider to use.
        storage_scope: The run's opaque storage prefix; normalized bytes land
            under `{storage_scope}/assets/`.

    Returns:
        A tuple of (normalized_list_content, has_changed).
    """
    raw_items = list_content.items  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    if not raw_items:
        return list_content, False

    normalized_items, has_changes = await _normalize_list(items=raw_items, storage=storage, storage_scope=storage_scope)  # pyright: ignore[reportUnknownArgumentType]

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
    *,
    storage: StorageProviderAbstract,
    storage_scope: str,
) -> tuple[list[Any], bool]:
    """Normalize a list by processing all its items.

    Args:
        items: The list items to normalize.
        storage: The storage provider to use.
        storage_scope: The run's opaque storage prefix; normalized bytes land
            under `{storage_scope}/assets/`.

    Returns:
        A tuple of (normalized_items, has_changed).
    """
    normalized_items: list[Any] = []
    has_changes = False

    for item in items:
        normalized_item, changed = await _normalize_value(value=item, storage=storage, storage_scope=storage_scope)
        normalized_items.append(normalized_item)
        if changed:
            has_changes = True

    return normalized_items, has_changes


async def _normalize_url_content(
    content: NormalizableContent,
    *,
    storage: StorageProviderAbstract,
    storage_scope: str,
) -> NormalizableContent:
    """Normalize ImageContent or DocumentContent by converting data URLs to storage URIs.

    Args:
        content: The image or document content to normalize.
        storage: The storage provider to use.
        storage_scope: The run's opaque storage prefix; normalized bytes land
            under `{storage_scope}/assets/`.

    Returns:
        The original content if no normalization needed, or a new instance
        with the normalized URL.
    """
    if not content.url.strip():
        msg = f"{type(content).__name__} input has a blank url — provide https://, data:, pipelex-storage://, or a local file path."
        raise PipelineInputUrlMissingError(msg)

    resolved_uri = resolve_uri(content.url)

    if isinstance(resolved_uri, ResolvedBase64DataUrl):
        # Decode base64 data and store
        raw_bytes = base64.b64decode(resolved_uri.base64_data)
        file_type = detect_file_type_from_bytes(raw_bytes)
        mime_type = resolved_uri.mime_type or content.mime_type
        # `{scope}/assets/`, NOT the old flat `normalized/`. That top-level
        # prefix was shared by every run of every tenant: the bytes of an input
        # someone pasted as a data: URL landed beside everyone else's, keyed
        # only by a random id. Under the run's own scope they are inside the
        # tenant's namespace and go away with the run.
        key = f"{storage_scope}/assets/{shortuuid.uuid()}.{file_type.extension}"
        storage_uri = await storage.store(data=raw_bytes, key=key, content_type=mime_type)
        public_url = await storage.public_url(uri=storage_uri)

        # Use model_copy to preserve all type-specific fields
        return content.model_copy(
            update={
                "url": storage_uri,
                "public_url": public_url,
                "mime_type": mime_type,
            }
        )
    elif isinstance(resolved_uri, ResolvedLocalPath):
        if not get_config().runtime.storage.is_upload_local_content_enabled:
            return content

        # Read local file, detect type, upload to storage. OSError covers
        # the whole caller-controllable failure surface (FileNotFoundError,
        # IsADirectoryError, PermissionError, name-too-long, ...) — all of
        # them mean the supplied path is unusable, an INPUT fault.
        try:
            raw_bytes = await load_binary_async(Path(resolved_uri.path))
        except OSError as exc:
            msg = f"Input file cannot be read: '{resolved_uri.path}' ({type(exc).__name__})"
            raise PipelineInputContentError(msg) from exc
        file_type = detect_file_type_from_bytes(raw_bytes)
        key = f"{storage_scope}/assets/{shortuuid.uuid()}.{file_type.extension}"
        storage_uri = await storage.store(data=raw_bytes, key=key, content_type=file_type.mime)
        public_url = await storage.public_url(uri=storage_uri)

        return content.model_copy(
            update={
                "url": storage_uri,
                "public_url": public_url,
                "mime_type": file_type.mime,
            }
        )
    else:
        # Other URI types (HTTP URLs, pipelex-storage://) are kept unchanged
        return content
