"""Turn any URI a value carries into a base64 data URL, fetching remote content as needed.

This lives apart from ``uri_resolver`` and ``base64_utils`` on purpose: resolving a URI and
encoding bytes are pure functions the kernel layer needs everywhere, while these two reach the
network through the fetch helper. Keeping them apart keeps the fetch helper, and the
configuration it reads, out of the kernel's import closure.
"""

from pathlib import Path

from pipelex.tools.misc.base64_utils import make_base64_url_from_bytes, make_base64_url_from_path
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)
from pipelex.tools.uri.uri_resolver import resolve_uri


async def make_base64_url_from_http_url(url: str) -> str:
    """Fetch a URL and create a data: URL from its contents.

    Raises:
        RemoteFileFetchError: The server answered with an error status, refused the
            connection, or did not answer in time.
        SsrfBlockedError: The destination, or a redirect hop's, is a private, loopback,
            link-local or metadata address.
    """
    raw_bytes = await fetch_file_from_url_httpx(url=url)
    return make_base64_url_from_bytes(raw_bytes=raw_bytes)


async def make_base64_url_from_any_uri(
    uri: str,
    *,
    storage_provider: StorageProviderAbstract | None = None,
) -> str:
    """Convert a URI to a base64 data URL.

    Resolves the URI and fetches/converts content to base64 format.
    If the URI is already a data URL, returns it as-is.

    Args:
        uri: A URI string (http://, local path, data: URL, or pipelex-storage://)
        storage_provider: Optional storage provider for resolving pipelex-storage:// URIs.
            Required when the URI is a pipelex-storage:// URI.

    Returns:
        A base64 data URL string containing the base64-encoded data, whichever way we got it.

    Raises:
        ValueError: If the URI is a pipelex-storage:// URI and no storage provider is given.
        SsrfBlockedError: If the URI is an http(s) URL whose destination, or a redirect hop's,
            is a private, loopback, link-local or metadata address.
    """
    base64_url: str
    resolved_uri = resolve_uri(uri)
    match resolved_uri:
        case ResolvedBase64DataUrl():
            # Already a data URL, return as-is
            base64_url = resolved_uri.original
        case ResolvedHttpUrl():
            base64_url = await make_base64_url_from_http_url(url=resolved_uri.url)
        case ResolvedLocalPath():
            base64_url = await make_base64_url_from_path(path=Path(resolved_uri.path))
        case ResolvedPipelexStorage():
            if storage_provider is None:
                msg = f"Cannot convert pipelex-storage:// URI to base64 without a storage provider: {uri}"
                raise ValueError(msg)
            raw_bytes = await storage_provider.load(uri=resolved_uri.storage_uri)
            base64_url = make_base64_url_from_bytes(raw_bytes=raw_bytes)
    return base64_url
