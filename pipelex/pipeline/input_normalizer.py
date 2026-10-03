"""Prepare a run's file inputs: establish each one's format, and relocate it to storage when configured.

This module walks the WorkingMemory a run starts from and visits every ImageContent and
DocumentContent, including list items and the fields nested in structured content. It does two
things to each:

- **Identification**, always (mock inputs aside, which the caller skips): the content's `mime_type`
  is stamped with the type that describes its bytes, so every later check and operator reads the
  format instead of guessing it again. The bytes are the truth: a sniffed type replaces a declared
  one. A stored file is identified by a head read of its first bytes, a data URL and a local file by
  the bytes already in hand. An http(s) input is never fetched, and keeps whatever type the caller
  declared. An Image input whose bytes identify something other than an image is refused here,
  before it is relocated, whatever will consume it.
- **Relocation**, when the run is configured for it: a data URL, or a local file when local uploads
  are enabled, is stored and its url becomes a `pipelex-storage://` reference, and every input gets
  a `public_url` a template can render.

`collect_file_inputs` then reads the stamped formats back, each with its path in the inputs
(`transcripts[2]`, `case.attachment`), for the checks that refuse a run before it starts.
"""

import asyncio
import base64
import binascii
from collections.abc import Coroutine, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, NamedTuple, TypeAlias, TypeVar, cast

import aiofiles
import shortuuid
from pydantic import BaseModel, ConfigDict

from pipelex.config import get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipeline.exceptions import (
    PipelineInputContentError,
    PipelineInputNotAnImageError,
    PipelineInputUrlInvalidError,
    PipelineInputUrlMissingError,
)
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import (
    FILE_HEAD_NB_BYTES,
    IMAGE_FORMAT_KEY,
    UNKNOWN_FILE_TYPE,
    describe_file_format,
    format_key_from_mime_type,
    guess_file_type_from_bytes,
    identify_mime_type,
    mime_type_to_extension,
)
from pipelex.tools.misc.http_utils import validate_http_url_syntax
from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageInvalidUriError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.resolved_uri import ResolvedBase64DataUrl, ResolvedHttpUrl, ResolvedLocalPath, ResolvedPipelexStorage, UriKind
from pipelex.tools.uri.uri_read_scope import authorize_uri_read
from pipelex.tools.uri.uri_resolver import resolve_uri

# Type alias for content types that can have their URLs normalized
NormalizableContent = ImageContent | DocumentContent

# Where a file sits in a run's inputs: the input's name, then field names and list indexes.
# `("transcripts", 2)` is `transcripts[2]`, `("case", "attachment")` is `case.attachment`.
FileInputPath: TypeAlias = tuple[str | int, ...]

# How many file inputs are prepared at once. A list of stored documents is identified by one head
# read each, and these overlap rather than costing a round-trip each in sequence.
MAX_CONCURRENT_FILE_IDENTIFICATIONS: Final[int] = 8

_ResultT = TypeVar("_ResultT")


class FileInputKind(StrEnum):
    """Which content class holds a file input: what the caller's input slot promises it is."""

    IMAGE = "image"
    DOCUMENT = "document"


class IdentifiedFileInput(BaseModel):
    """One file input of a run, with the format its preparation established."""

    model_config = ConfigDict(frozen=True)

    path: FileInputPath
    kind: FileInputKind
    uri_kind: UriKind
    mime_type: str | None

    @property
    def display_path(self) -> str:
        """The path as a caller reads it: `transcripts[2]`, `case.attachment`."""
        return format_file_input_path(self.path)

    @property
    def format_key(self) -> str | None:
        """The key every format check compares, `None` when the format is unknown."""
        return format_key_from_mime_type(mime_type=self.mime_type)


class _PreparationContext(NamedTuple):
    """What every visited file input is prepared with, shared by the whole walk."""

    storage: StorageProviderAbstract
    storage_scope: str
    read_scope: str | None
    is_relocation_enabled: bool
    semaphore: asyncio.Semaphore


def format_file_input_path(path: FileInputPath) -> str:
    """Render a file input's path the way a caller writes it: `transcripts[2]`, `case.attachments[0]`."""
    rendered = ""
    for segment in path:
        if isinstance(segment, int):
            rendered += f"[{segment}]"
        elif rendered:
            rendered += f".{segment}"
        else:
            rendered = segment
    return rendered


async def prepare_file_inputs(
    working_memory: WorkingMemory,
    *,
    storage_scope: str,
    read_scope: str | None,
    is_relocation_enabled: bool,
) -> WorkingMemory:
    """Establish the format of every file input, and relocate it to storage when configured.

    Visits every ImageContent and DocumentContent in the working memory, including the items of a
    list and the fields of a structured content, recursively. The images inside a
    TextAndImagesContent are not reached, and keep their url, public_url and mime_type as given.
    File inputs are prepared concurrently, at most `MAX_CONCURRENT_FILE_IDENTIFICATIONS` at a time.
    See `_prepare_url_content` for what happens to each form of url.

    Args:
        working_memory: The working memory to prepare. Its stuffs are updated in place.
        storage_scope: The run's opaque storage prefix. Relocated bytes land under
            `{storage_scope}/assets/`, inside the run's own namespace.
        read_scope: The run's read scope. On a scoped run every url is authorized before it is
            read or linked: a local path is refused instead of being read, uploaded or kept for a
            later reader, and a storage reference outside the scope is refused instead of being
            read or signed, since a signed link is a read. The refusal names the input. ``None``
            for an unscoped run. See :mod:`pipelex.tools.uri.uri_read_scope`.
        is_relocation_enabled: Whether data URLs and local files are stored and every input gets a
            `public_url`. Identification runs either way.

    Returns:
        The same WorkingMemory instance, its file inputs stamped with their `mime_type`.

    Raises:
        PipelineInputUrlMissingError: An input's url is blank.
        PipelineInputNotAnImageError: An Image input's bytes identify something other than an image.
        PipelineInputUrlInvalidError: An http(s) url does not parse as one (when relocating).
        PipelineInputContentError: A data URL is not valid base64, a local path cannot be read
            for an upload, or a storage reference names no stored file or is refused as a key.
        UriReadRefusedError: An input's url is a local path, or a storage reference outside the
            read scope, on a run with a read scope.
    """
    context = _PreparationContext(
        storage=get_storage_provider(),
        storage_scope=storage_scope,
        read_scope=read_scope,
        is_relocation_enabled=is_relocation_enabled,
        semaphore=asyncio.Semaphore(MAX_CONCURRENT_FILE_IDENTIFICATIONS),
    )
    named_stuffs = list(working_memory.root.items())
    results = await _gather_cancelling(
        coroutines=[_prepare_value(value=stuff.content, path=(input_name,), context=context) for input_name, stuff in named_stuffs]
    )
    for (_input_name, stuff), (prepared_content, changed) in zip(named_stuffs, results, strict=True):
        if changed:
            stuff.content = prepared_content
    return working_memory


def collect_file_inputs(working_memory: WorkingMemory) -> list[IdentifiedFileInput]:
    """Every file input of the working memory, with its path and the `mime_type` it carries.

    Pure: it reads what `prepare_file_inputs` stamped and does no IO. The walk is the same, so the
    images inside a TextAndImagesContent are not reached either.
    """
    file_inputs: list[IdentifiedFileInput] = []
    for input_name, stuff in working_memory.root.items():
        _collect_value(value=stuff.content, path=(input_name,), file_inputs=file_inputs)
    return file_inputs


def _collect_value(*, value: Any, path: FileInputPath, file_inputs: list[IdentifiedFileInput]) -> None:
    if isinstance(value, (ImageContent, DocumentContent)):
        file_inputs.append(
            IdentifiedFileInput(
                path=path,
                kind=FileInputKind.IMAGE if isinstance(value, ImageContent) else FileInputKind.DOCUMENT,
                uri_kind=resolve_uri(value.url).kind,
                mime_type=value.mime_type,
            )
        )
    elif isinstance(value, StructuredContent):
        for field_name, field_value in value:
            _collect_value(value=field_value, path=(*path, field_name), file_inputs=file_inputs)
    elif isinstance(value, ListContent):
        list_items = cast("list[Any]", value.items)  # pyright: ignore[reportUnknownMemberType]
        for item_index, item in enumerate(list_items):
            _collect_value(value=item, path=(*path, item_index), file_inputs=file_inputs)
    elif isinstance(value, list):
        for item_index, item in enumerate(cast("list[Any]", value)):
            _collect_value(value=item, path=(*path, item_index), file_inputs=file_inputs)


async def _gather_cancelling(*, coroutines: Sequence[Coroutine[Any, Any, _ResultT]]) -> list[_ResultT]:
    """Run the coroutines concurrently and return their results in order.

    On the first failure the others are cancelled and awaited before the failure propagates, as
    itself and not wrapped in a group, so a caller's error mapping sees the input error it raised.
    """
    tasks = [asyncio.ensure_future(coroutine) for coroutine in coroutines]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def _prepare_value(*, value: Any, path: FileInputPath, context: _PreparationContext) -> tuple[Any, bool]:
    """Recursively prepare a value, returning the prepared value and whether it changed."""
    if isinstance(value, (ImageContent, DocumentContent)):
        prepared = await _prepare_url_content(content=value, path=path, context=context)
        return prepared, prepared is not value

    if isinstance(value, StructuredContent):
        return await _prepare_structured_content(structured_content=value, path=path, context=context)

    if isinstance(value, ListContent):
        return await _prepare_list_content(
            list_content=value,  # pyright: ignore[reportUnknownArgumentType]
            path=path,
            context=context,
        )

    # Plain lists, which might contain ImageContent, DocumentContent, or StructuredContent
    if isinstance(value, list):
        return await _prepare_list(
            items=value,  # pyright: ignore[reportUnknownArgumentType]
            path=path,
            context=context,
        )

    # Other types don't need preparation
    return value, False


async def _prepare_structured_content(
    *,
    structured_content: StructuredContent,
    path: FileInputPath,
    context: _PreparationContext,
) -> tuple[StructuredContent, bool]:
    """Prepare a StructuredContent by preparing all its fields."""
    fields = list(structured_content)
    results = await _gather_cancelling(
        coroutines=[_prepare_value(value=field_value, path=(*path, field_name), context=context) for field_name, field_value in fields]
    )
    updates: dict[str, Any] = {}
    for (field_name, _field_value), (prepared_value, changed) in zip(fields, results, strict=True):
        if changed:
            updates[field_name] = prepared_value

    if not updates:
        return structured_content, False

    # model_copy with update preserves all other fields
    return structured_content.model_copy(update=updates), True


async def _prepare_list_content(
    *,
    list_content: ListContent[Any],
    path: FileInputPath,
    context: _PreparationContext,
) -> tuple[ListContent[Any], bool]:
    """Prepare a ListContent by preparing all its items."""
    raw_items = list_content.items  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
    if not raw_items:
        return list_content, False

    prepared_items, has_changes = await _prepare_list(items=raw_items, path=path, context=context)  # pyright: ignore[reportUnknownArgumentType]

    if not has_changes:
        return list_content, False

    # Check the type of the first item to determine the ListContent type
    first_item = prepared_items[0]
    if isinstance(first_item, ImageContent):
        return ListContent[ImageContent](items=cast("list[ImageContent]", prepared_items)), True
    if isinstance(first_item, DocumentContent):
        return ListContent[DocumentContent](items=cast("list[DocumentContent]", prepared_items)), True

    # For other types (e.g., StructuredContent subclasses), use generic ListContent
    return ListContent(items=prepared_items), True


async def _prepare_list(
    *,
    items: list[Any],
    path: FileInputPath,
    context: _PreparationContext,
) -> tuple[list[Any], bool]:
    """Prepare a list by preparing all its items, each at its index."""
    results = await _gather_cancelling(
        coroutines=[_prepare_value(value=item, path=(*path, item_index), context=context) for item_index, item in enumerate(items)]
    )
    prepared_items = [prepared_item for prepared_item, _changed in results]
    has_changes = any(changed for _prepared_item, changed in results)
    return prepared_items, has_changes


async def _prepare_url_content(
    *,
    content: NormalizableContent,
    path: FileInputPath,
    context: _PreparationContext,
) -> NormalizableContent:
    """Identify one ImageContent or DocumentContent, and relocate it when configured.

    Every form comes out with its `mime_type` established, and, when relocating, with a
    `public_url` a template can render:

    - A `data:` URL is decoded and identified from its bytes. When relocating, it is stored, its
      url becomes the storage reference, signed as its `public_url`.
    - A local path is identified from its bytes. When relocating with local uploads enabled, it is
      stored the same way; otherwise it is kept, and identified from a head read of the file.
    - A `pipelex-storage://` reference is identified from a head read of the stored object. When
      relocating, it is signed as its `public_url`, replacing any link it carried, which may have
      expired; a provider that cannot link one leaves the carried link.
    - An `http(s)` URL is never fetched and keeps its declared type. When relocating, its syntax is
      checked and it becomes its own `public_url` unless the input names one.

    Raises:
        PipelineInputUrlMissingError: If the url is blank.
        PipelineInputNotAnImageError: If the content is an ImageContent and its bytes identify
            something other than an image. It is raised before anything is relocated.
        PipelineInputUrlInvalidError: If an http(s) url does not parse as one (when relocating).
        PipelineInputContentError: If a data URL is not valid base64, a local path cannot be read
            for an upload, or a pipelex-storage:// reference names no stored file or is refused
            by the storage provider as a key.
        UriReadRefusedError: If the url is a local path, or a storage reference outside the
            read scope, on a run with a read scope.
    """
    input_name = format_file_input_path(path)
    if not content.url.strip():
        msg = f"{type(content).__name__} input has a blank url — provide https://, data:, pipelex-storage://, or a local file path."
        raise PipelineInputUrlMissingError(msg)

    # Before anything reads or links the url. A signed link is a read by whoever holds it, so a
    # foreign storage reference is refused here rather than read or signed; a local path is refused
    # rather than read, uploaded, or kept for the prompt preparation to read later.
    authorize_uri_read(uri=content.url, read_scope=context.read_scope, position=f"the file given for input '{input_name}'")

    resolved_uri = resolve_uri(content.url)
    async with context.semaphore:
        match resolved_uri:
            case ResolvedHttpUrl():
                return _prepare_http_url(content=content, resolved_uri=resolved_uri, context=context)
            case ResolvedPipelexStorage():
                return await _prepare_storage_reference(content=content, resolved_uri=resolved_uri, input_name=input_name, context=context)
            case ResolvedBase64DataUrl():
                return await _prepare_data_url(content=content, resolved_uri=resolved_uri, input_name=input_name, context=context)
            case ResolvedLocalPath():
                return await _prepare_local_path(content=content, resolved_uri=resolved_uri, input_name=input_name, context=context)


def _prepare_http_url(*, content: NormalizableContent, resolved_uri: ResolvedHttpUrl, context: _PreparationContext) -> NormalizableContent:
    # Never fetched: setup makes no outbound request to a host the caller chose. The operator that
    # consumes the input fetches it, reports a real failure, and checks the format of the bytes.
    if not context.is_relocation_enabled:
        return content
    # Syntax only, no network: the operator's fetch is the one honest test of a remote resource.
    try:
        validate_http_url_syntax(url=resolved_uri.url)
    except ValueError as exc:
        msg = f"{type(content).__name__} input: {exc}"
        raise PipelineInputUrlInvalidError(msg) from exc
    if content.public_url is not None:
        return content
    return content.model_copy(update={"public_url": content.url})


async def _prepare_storage_reference(
    *,
    content: NormalizableContent,
    resolved_uri: ResolvedPipelexStorage,
    input_name: str,
    context: _PreparationContext,
) -> NormalizableContent:
    try:
        head = await context.storage.load_head(uri=resolved_uri.storage_uri, nb_bytes=FILE_HEAD_NB_BYTES)
    except StorageFileNotFoundError as exc:
        msg = f"{type(content).__name__} input '{input_name}': the storage reference '{content.url}' names no stored file"
        raise PipelineInputContentError(msg) from exc
    except StorageInvalidUriError as exc:
        msg = f"{type(content).__name__} input '{input_name}': the storage reference '{content.url}' cannot be read ({exc})"
        raise PipelineInputContentError(msg) from exc
    updates: dict[str, Any] = {}
    mime_type = _identify_file_input(content=content, head=head, declared_mime_type=content.mime_type, input_name=input_name)
    if mime_type != content.mime_type:
        updates["mime_type"] = mime_type

    if context.is_relocation_enabled:
        # The reference is the durable fact and the link a derivative with an expiry, so the link is
        # always signed afresh: an input carrying both is usually a previous run's output passed back in.
        try:
            public_url = await context.storage.public_url(uri=resolved_uri.storage_uri)
        except StorageInvalidUriError as exc:
            msg = f"{type(content).__name__} input: the storage reference '{content.url}' cannot be linked ({exc})"
            raise PipelineInputContentError(msg) from exc
        if public_url is not None:
            updates["public_url"] = public_url

    if not updates:
        return content
    return content.model_copy(update=updates)


async def _prepare_data_url(
    *,
    content: NormalizableContent,
    resolved_uri: ResolvedBase64DataUrl,
    input_name: str,
    context: _PreparationContext,
) -> NormalizableContent:
    # Lenient on purpose, as it always was: characters outside the alphabet, such as the line breaks
    # of wrapped base64, are skipped. Only a payload that cannot decode at all is refused.
    try:
        raw_bytes = base64.b64decode(resolved_uri.base64_data)
    except binascii.Error as exc:
        msg = f"{type(content).__name__} input '{input_name}': the data URL does not hold valid base64 ({exc})"
        raise PipelineInputContentError(msg) from exc
    mime_type = _identify_file_input(
        content=content, head=raw_bytes[:FILE_HEAD_NB_BYTES], declared_mime_type=resolved_uri.mime_type or content.mime_type, input_name=input_name
    )

    if not context.is_relocation_enabled:
        if mime_type == content.mime_type:
            return content
        return content.model_copy(update={"mime_type": mime_type})

    # `{scope}/assets/`, NOT the old flat `normalized/`. That top-level
    # prefix was shared by every run of every tenant: the bytes of an input
    # someone pasted as a data: URL landed beside everyone else's, keyed
    # only by a random id. Under the run's own scope they are inside the
    # tenant's namespace and go away with the run.
    extension = _storage_key_extension(raw_bytes=raw_bytes, mime_type=mime_type, fallback_suffix=None)
    key = f"{context.storage_scope}/assets/{shortuuid.uuid()}.{extension}"
    storage_uri = await context.storage.store(data=raw_bytes, key=key, content_type=mime_type)
    public_url = await context.storage.public_url(uri=storage_uri)

    # model_copy preserves all type-specific fields
    return content.model_copy(
        update={
            "url": storage_uri,
            "public_url": public_url,
            "mime_type": mime_type,
        }
    )


async def _prepare_local_path(
    *,
    content: NormalizableContent,
    resolved_uri: ResolvedLocalPath,
    input_name: str,
    context: _PreparationContext,
) -> NormalizableContent:
    local_path = Path(resolved_uri.path)
    if not (context.is_relocation_enabled and get_config().runtime.storage.is_upload_local_content_enabled):
        # Kept for its consumer to read. A path that cannot be read here is left unidentified: whoever
        # reads it later reports that failure, as it did before identification existed.
        try:
            head = await _load_local_head(local_path)
        except (OSError, ValueError):
            return content
        mime_type = _identify_file_input(content=content, head=head, declared_mime_type=content.mime_type, input_name=input_name)
        if mime_type == content.mime_type:
            return content
        return content.model_copy(update={"mime_type": mime_type})

    # Read the local file, identify it, upload it to storage. OSError covers
    # the caller-controllable failure surface (FileNotFoundError,
    # IsADirectoryError, PermissionError, name-too-long, ...) and ValueError
    # the one left, a NUL byte in the path — all of them mean the supplied
    # path is unusable, an INPUT fault.
    try:
        raw_bytes = await load_binary_async(local_path)
    except (OSError, ValueError) as exc:
        msg = f"Input file cannot be read: '{resolved_uri.path}' ({type(exc).__name__})"
        raise PipelineInputContentError(msg) from exc
    mime_type = _identify_file_input(
        content=content, head=raw_bytes[:FILE_HEAD_NB_BYTES], declared_mime_type=content.mime_type, input_name=input_name
    )
    extension = _storage_key_extension(raw_bytes=raw_bytes, mime_type=mime_type, fallback_suffix=local_path.suffix.removeprefix(".") or None)
    key = f"{context.storage_scope}/assets/{shortuuid.uuid()}.{extension}"
    storage_uri = await context.storage.store(data=raw_bytes, key=key, content_type=mime_type)
    public_url = await context.storage.public_url(uri=storage_uri)

    return content.model_copy(
        update={
            "url": storage_uri,
            "public_url": public_url,
            "mime_type": mime_type,
        }
    )


def _identify_file_input(*, content: NormalizableContent, head: bytes | None, declared_mime_type: str | None, input_name: str) -> str | None:
    """The MIME type that describes a file input, refusing an Image input whose bytes are not an image.

    The type comes from `identify_mime_type`: the sniffed type wins, the declared one stands when the
    sniff fails. The refusal fires only when the bytes were identified, so an image the sniffer cannot
    identify, an SVG for one, is left to its consumer, and so is a type the caller merely declared.

    Raises:
        PipelineInputNotAnImageError: If the content is an ImageContent and its bytes identify a
            format other than an image.
    """
    mime_type = identify_mime_type(head=head, declared_mime_type=declared_mime_type)
    if not isinstance(content, ImageContent) or not head or guess_file_type_from_bytes(raw_bytes=head) is None:
        return mime_type
    format_key = format_key_from_mime_type(mime_type=mime_type)
    if format_key is None or format_key == IMAGE_FORMAT_KEY:
        return mime_type
    msg = (
        f"Input '{input_name}' expects an image, but the file is {describe_file_format(format_key=format_key, mime_type=mime_type)}. "
        "Give an image file such as PNG, JPEG or WebP."
    )
    raise PipelineInputNotAnImageError(msg)


async def _load_local_head(local_path: Path) -> bytes:
    """The first bytes of a local file, which is all identifying it needs."""
    async with aiofiles.open(local_path, "rb") as file_handle:  # pyright: ignore[reportUnknownMemberType]
        return await file_handle.read(FILE_HEAD_NB_BYTES)


def _storage_key_extension(*, raw_bytes: bytes, mime_type: str | None, fallback_suffix: str | None) -> str:
    """The extension a relocated file's storage key ends with.

    The sniffed extension when the bytes were identified, else the extension of the declared type,
    else the local file's own suffix, else `bin`.
    """
    sniffed = guess_file_type_from_bytes(raw_bytes=raw_bytes)
    if sniffed is not None and sniffed.mime == mime_type:
        return sniffed.extension
    if mime_type:
        extension = mime_type_to_extension(mime_type)
        if extension != UNKNOWN_FILE_TYPE:
            return extension
    return fallback_suffix or "bin"
