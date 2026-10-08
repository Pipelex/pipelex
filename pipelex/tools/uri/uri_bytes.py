"""Load the bytes behind any URI a value carries, with the media type its source gives them, fetching remote content as needed.

It sits beside `uri_base64` and apart from `uri_resolver` for the same reason: resolving a URI is a pure
function the kernel layer needs everywhere, while loading one reaches the network through the fetch helper,
which is kept out of the kernel's import closure. Loading does not check the run's read scope: a caller that
reads a value's URL authorizes it first (`uri_read_scope`).

The media type is the one the source gives, never a guess: the response's `Content-Type` for `https://`, the
type a `data:` URL declares, and the type the storage provider has for a `pipelex-storage://` key. A local
path has none, since a file system records no type. A caller that needs a type when the source gives none
guesses it itself, from the URI or the bytes, because only it knows what it needs the type for.
"""

import base64
from pathlib import Path
from typing import NamedTuple

from pipelex.tools.misc.file_fetch_utils import fetch_file_and_content_type_from_url_httpx
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import base_mime_type
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)
from pipelex.tools.uri.uri_resolver import resolve_uri


class UriBytes(NamedTuple):
    """The bytes a URI points at, and the media type its source gives them."""

    data: bytes
    mime_type: str | None = None


async def load_bytes_and_mime_type_from_any_uri(
    uri: str,
    *,
    storage_provider: StorageProviderAbstract | None = None,
) -> UriBytes:
    """Load the bytes a URI points at, whichever kind of URI it is, with the media type its source gives them.

    The type is lowercased and without its parameters (`text/css`, never `Text/CSS; charset=utf-8`), and it is
    `None` when the source gives none: an `https://` response without a `Content-Type`, a storage provider that
    has no type for the key, a `data:` URL declaring none, and every local path. A declared type is returned as
    declared, even a generic one such as `application/octet-stream`, and is not checked against the bytes.

    Args:
        uri: A URI string (http(s)://, a local path, a data: URL, or pipelex-storage://)
        storage_provider: The storage provider that resolves pipelex-storage:// URIs.
            Required when the URI is a pipelex-storage:// URI.

    Raises:
        ValueError: If the URI is a pipelex-storage:// URI and no storage provider is given.
        RemoteFileFetchError: The server answered with an error status, refused the connection, or did not answer in time.
        SsrfBlockedError: The destination, or a redirect hop's, is a private, loopback, link-local or metadata address.
    """
    raw_bytes: bytes
    declared_mime_type: str | None
    resolved_uri = resolve_uri(uri)
    match resolved_uri:
        case ResolvedBase64DataUrl():
            raw_bytes = base64.b64decode(resolved_uri.base64_data)
            declared_mime_type = resolved_uri.mime_type
        case ResolvedHttpUrl():
            raw_bytes, declared_mime_type = await fetch_file_and_content_type_from_url_httpx(resolved_uri.url)
        case ResolvedLocalPath():
            raw_bytes = await load_binary_async(path=Path(resolved_uri.path))
            declared_mime_type = None
        case ResolvedPipelexStorage():
            if storage_provider is None:
                msg = f"Cannot load a pipelex-storage:// URI without a storage provider: {uri}"
                raise ValueError(msg)
            raw_bytes, declared_mime_type = await storage_provider.load_with_metadata(uri=resolved_uri.storage_uri)
    mime_type = base_mime_type(mime_type=declared_mime_type) if declared_mime_type else None
    return UriBytes(data=raw_bytes, mime_type=mime_type or None)


async def load_bytes_from_any_uri(
    uri: str,
    *,
    storage_provider: StorageProviderAbstract | None = None,
) -> bytes:
    """Load the bytes a URI points at, whichever kind of URI it is, for a caller that has no use for their media type.

    Raises:
        ValueError: If the URI is a pipelex-storage:// URI and no storage provider is given.
        RemoteFileFetchError: The server answered with an error status, refused the connection, or did not answer in time.
        SsrfBlockedError: The destination, or a redirect hop's, is a private, loopback, link-local or metadata address.
    """
    loaded = await load_bytes_and_mime_type_from_any_uri(uri, storage_provider=storage_provider)
    return loaded.data
