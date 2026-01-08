"""Utilities for preparing files from URIs.

This module provides functions to convert URI strings into PreparedFile
instances that can be consumed by various APIs.
"""

import base64

from pipelex.hub import get_storage_provider
from pipelex.tools.misc.file_fetch_utils import fetch_file_from_url_httpx
from pipelex.tools.misc.file_utils import load_binary_async
from pipelex.tools.misc.filetype_utils import detect_file_type_from_base64, detect_file_type_from_bytes
from pipelex.tools.uri.prepared_file import PreparedFile, PreparedFileBase64, PreparedFileHttpUrl, PreparedFileLocalPath
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
)
from pipelex.tools.uri.uri_resolver import resolve_uri


async def prepare_file_from_uri(
    uri: str,
    keep_http_url: bool,
    keep_local_path: bool,
) -> PreparedFile:
    """Prepare a file from a URI for consumption by various APIs.

    Args:
        uri: The URI string to resolve and prepare (HTTP URL, local path, storage URI, or data URL)
        keep_http_url: If True, return HTTP URLs as-is instead of downloading and converting to base64
        keep_local_path: If True, return local paths as-is instead of loading and converting to base64

    Returns:
        A PreparedFile (HttpUrl, LocalPath, or Base64) ready for consumption

    Example:
        >>> # Convert HTTP URL to base64
        >>> prepared = await prepare_file_from_uri("https://example.com/file.pdf")
        >>> isinstance(prepared, PreparedFileBase64)
        True

        >>> # Keep HTTP URL as-is
        >>> prepared = await prepare_file_from_uri("https://example.com/file.pdf", keep_http_url=True)
        >>> isinstance(prepared, PreparedFileHttpUrl)
        True

        >>> # Keep local path as-is
        >>> prepared = await prepare_file_from_uri("/path/to/file.txt", keep_local_path=True)
        >>> isinstance(prepared, PreparedFileLocalPath)
        True
    """
    prepared: PreparedFile
    resolved_uri = resolve_uri(uri)

    match resolved_uri:
        case ResolvedHttpUrl():
            if keep_http_url:
                prepared = PreparedFileHttpUrl(url=resolved_uri.url)
            else:
                raw_bytes = await fetch_file_from_url_httpx(url=resolved_uri.url)
                prepared = PreparedFileBase64(
                    base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                    file_type=detect_file_type_from_bytes(raw_bytes),
                )

        case ResolvedLocalPath():
            if keep_local_path:
                prepared = PreparedFileLocalPath(path=resolved_uri.path)
            else:
                raw_bytes = await load_binary_async(resolved_uri.path)
                prepared = PreparedFileBase64(
                    base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                    file_type=detect_file_type_from_bytes(raw_bytes),
                )

        case ResolvedPipelexStorage():
            # TODO: possibility to keep http url or local path if applicable
            storage = get_storage_provider()
            raw_bytes = await storage.load(uri=resolved_uri.storage_uri)
            prepared = PreparedFileBase64(
                base64_data=base64.b64encode(raw_bytes).decode("ascii"),
                file_type=detect_file_type_from_bytes(raw_bytes),
            )

        case ResolvedBase64DataUrl():
            # TODO: possibility to not keep base64 data url
            # base64_data from ResolvedBase64DataUrl is already a string
            base64_data = resolved_uri.base64_data
            prepared = PreparedFileBase64(
                base64_data=base64_data,
                file_type=detect_file_type_from_base64(base64_data),
            )

    return prepared
