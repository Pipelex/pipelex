import urllib.parse

from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
    ResolvedUri,
)

# Base64 data URL markers
BASE64_DATA_URL_PREFIX = "data:"
BASE64_DATA_URL_MARKER = ";base64,"


def resolve_uri(uri: str) -> ResolvedUri:
    """Resolve a URI string to its typed representation.

    This function parses the input string and returns the appropriate
    ResolvedUri variant based on the URI type:

    - HTTP/HTTPS URLs -> ResolvedHttpUrl
    - file:// URIs -> ResolvedLocalPath (converted to path)
    - Local paths -> ResolvedLocalPath
    - pipelex-storage:// URIs -> ResolvedPipelexStorage
    - data:...;base64,... URLs -> ResolvedBase64DataUrl

    Args:
        uri: The URI string to resolve.

    Returns:
        A ResolvedUri variant with the parsed URI information.

    Example:
        >>> resolved_uri = resolve_uri("https://example.com/image.png")
        >>> resolved_uri.kind
        UriKind.HTTP_URL
        >>> resolved_uri.url
        'https://example.com/image.png'

        >>> resolved_uri = resolve_uri("pipelex-storage://images/photo.png")
        >>> resolved_uri.kind
        UriKind.PIPELEX_STORAGE
        >>> resolved_uri.storage_uri
        'pipelex-storage://images/photo.png'
    """
    # Check for base64 data URLs first (data:{mime};base64,{data})
    if uri.startswith(BASE64_DATA_URL_PREFIX) and BASE64_DATA_URL_MARKER in uri:
        return _resolve_base64_data_url(uri)

    # Check for pipelex storage URIs
    if uri.startswith(PIPELEX_STORAGE_SCHEME):
        return ResolvedPipelexStorage(
            original=uri,
            storage_uri=uri,
        )

    # Check for file:// URIs
    if uri.startswith("file://"):
        return _resolve_file_uri(uri)

    # Check for HTTP/HTTPS URLs
    if uri.startswith(("http://", "https://")):
        return ResolvedHttpUrl(
            original=uri,
            url=uri,
        )

    # Everything else is a local path (absolute, relative, or filename)
    return ResolvedLocalPath(
        original=uri,
        path=uri,
    )


def _resolve_file_uri(uri: str) -> ResolvedLocalPath:
    """Convert a file:// URI to a local path.

    Args:
        uri: A file:// URI string.

    Returns:
        ResolvedLocalPath with the converted path.
    """
    parsed = urllib.parse.urlparse(uri)
    path = urllib.parse.unquote(parsed.path)
    return ResolvedLocalPath(
        original=uri,
        path=path,
    )


def _resolve_base64_data_url(uri: str) -> ResolvedBase64DataUrl:
    """Parse a base64 data URL into its components.

    Args:
        uri: A data URL in the format data:{mime};base64,{data}

    Returns:
        ResolvedBase64DataUrl with mime_type and base64_data.
    """
    # Format: data:{mime_type};base64,{base64_data}
    # Remove "data:" prefix
    content = uri[len(BASE64_DATA_URL_PREFIX) :]

    # Split on ;base64,
    parts = content.split(BASE64_DATA_URL_MARKER, 1)
    mime_type = parts[0]
    base64_data = parts[1] if len(parts) > 1 else ""

    return ResolvedBase64DataUrl(
        original=uri,
        mime_type=mime_type,
        base64_data=base64_data,
    )
