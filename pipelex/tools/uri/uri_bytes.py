"""Load the bytes behind any URI a value carries, fetching remote content as needed.

It sits beside `uri_base64` and apart from `uri_resolver` for the same reason: resolving a URI is a pure
function the kernel layer needs everywhere, while loading one reaches the network through the fetch helper,
which is kept out of the kernel's import closure. Loading does not check the run's read scope: a caller that
reads a value's URL authorizes it first (`uri_read_scope`).
"""

import base64
from pathlib import Path

from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)
from pipelex.tools.uri.uri_resolver import resolve_uri


async def load_bytes_from_any_uri(
    uri: str,
    *,
    storage_provider: StorageProviderAbstract | None = None,
) -> bytes:
    """Load the bytes a URI points at, whichever kind of URI it is.

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
    resolved_uri = resolve_uri(uri)
    match resolved_uri:
        case ResolvedBase64DataUrl():
            raw_bytes = base64.b64decode(resolved_uri.base64_data)
        case ResolvedHttpUrl():
            raw_bytes = await fetch_file_from_url_httpx(url=resolved_uri.url)
        case ResolvedLocalPath():
            raw_bytes = await load_binary_async(path=Path(resolved_uri.path))
        case ResolvedPipelexStorage():
            if storage_provider is None:
                msg = f"Cannot load a pipelex-storage:// URI without a storage provider: {uri}"
                raise ValueError(msg)
            raw_bytes = await storage_provider.load(uri=resolved_uri.storage_uri)
    return raw_bytes
