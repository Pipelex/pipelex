import urllib.parse
from pathlib import Path

from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME
from pipelex.tools.uri.data_url import is_data_url, parse_base64_data_url
from pipelex.tools.uri.resolved_uri import (
    ResolvedBase64DataUrl,
    ResolvedHttpUrl,
    ResolvedLocalPath,
    ResolvedPipelexStorage,
    ResolvedUri,
    UriKind,
)


def extract_filename_from_uri(uri: str) -> str | None:
    """Extract a filename from a URI, only for local file paths.

    Args:
        uri: The URI string to extract the filename from.

    Returns:
        The filename if the URI is a local file path, None otherwise.
    """
    if is_data_url(uri=uri):
        # A data URL names no file, whether or not it is one this runtime reads.
        return None
    resolved = resolve_uri(uri)
    match resolved:
        case ResolvedLocalPath():
            name = Path(resolved.path).name
            return name or None
        case ResolvedHttpUrl():
            return None
        case ResolvedBase64DataUrl():
            return None
        case ResolvedPipelexStorage():
            return None


def describe_uri(uri: str) -> str:
    """Describe a URI string.

    Args:
        uri: The URI string to describe.

    Returns:
        A human-readable description of the URI.
    """
    if is_data_url(uri=uri):
        # Described without being parsed, so describing a data URL this runtime does not read never fails.
        return UriKind.BASE64_DATA_URL.desc
    resolved_uri = resolve_uri(uri)
    return resolved_uri.kind.desc


def is_relative_local_path(uri: str) -> bool:
    """Check whether *uri* is a relative local file path.

    Uses :func:`resolve_uri` to classify the URI.  Returns ``True`` only when
    the URI resolves to a :class:`ResolvedLocalPath` **and** the path is not
    absolute.

    Args:
        uri: The URI string to check.

    Returns:
        ``True`` if *uri* is a relative local path, ``False`` otherwise.
    """
    if is_data_url(uri=uri):
        return False
    resolved = resolve_uri(uri)
    if not isinstance(resolved, ResolvedLocalPath):
        return False
    if "://" in resolved.path:
        # An unrecognized scheme (``s3://``, ``gs://``, …) slips through ``resolve_uri`` as a
        # ResolvedLocalPath but is NOT a local file path; do not treat it as relative
        # (that would let a caller mangle ``s3://bucket/x`` into ``<base_dir>/s3:/bucket/x`` and
        # defeat the downstream remote-url guards). Mirrors the same ``"://"`` stopgap in the CSV
        # input hook; both go away once ``resolve_uri`` classifies schemes (tools/uri follow-up).
        return False
    return not Path(resolved.path).is_absolute()


def resolve_local_path_reference(uri: str, *, base_dir: Path | None) -> str:
    """Expand a leading ``~`` to the user's home, then resolve a still-relative local path against
    *base_dir* (D3).

    ``~/photo.jpg`` → ``<home>/photo.jpg`` (absolute — never joined onto *base_dir*); a genuine
    relative local path → ``<base_dir>/<path>`` when *base_dir* is given, else unchanged (the CWD
    contract); an absolute path or any remote/scheme URI → unchanged. Mirrors the CLI's expanduser of
    the inputs-file arg itself (``_inputs_file_loader``/``_run_core``/``stdin_resolver``), extended to
    the file-ish input *values* — the shaper's file/CSV arms and the CLI's url-key walk share it.

    Args:
        uri: The path/URL reference to resolve (a bare input value or a ``{"url": ...}`` value).
        base_dir: Directory that a still-relative local path resolves against; ``None`` leaves a
            relative path untouched (in-process / inline-JSON callers keep the CWD contract).

    Returns:
        The resolved reference string.
    """
    expanded = str(Path(uri).expanduser()) if uri.startswith("~") else uri
    if base_dir is not None and is_relative_local_path(expanded):
        return str(base_dir / expanded)
    return expanded


def resolve_uri(uri: str) -> ResolvedUri:
    """Resolve a URI string to its typed representation.

    This function parses the input string and returns the appropriate
    ResolvedUri variant based on the URI type:

    - HTTP/HTTPS URLs -> ResolvedHttpUrl
    - file:// URIs -> ResolvedLocalPath (converted to path)
    - Local paths -> ResolvedLocalPath
    - pipelex-storage:// URIs -> ResolvedPipelexStorage
    - data:...;base64,... URLs -> ResolvedBase64DataUrl, the scheme in any ASCII case, read by
      :func:`pipelex.tools.uri.data_url.parse_data_url`, whose header ends at its first comma

    Args:
        uri: The URI string to resolve.

    Returns:
        A ResolvedUri variant with the parsed URI information.

    Raises:
        DataUrlError: `uri` is a `data:` URL that is not a base64 one, or holds no comma ending its header.

    Example:
        >>> resolved_uri = resolve_uri("https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/png_example.png")
        >>> resolved_uri.kind
        UriKind.HTTP_URL
        >>> resolved_uri.url
        'https://pipelex-pytest-assets.s3.eu-west-3.amazonaws.com/png_example.png'

        >>> resolved_uri = resolve_uri("pipelex-storage://images/photo.png")
        >>> resolved_uri.kind
        UriKind.PIPELEX_STORAGE
        >>> resolved_uri.storage_uri
        'pipelex-storage://images/photo.png'
    """
    # Every data URL is read by the one parser, and only a base64 one resolves: no other reader of its bytes exists.
    if is_data_url(uri=uri):
        return _resolve_base64_data_url(uri=uri)

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


def _resolve_base64_data_url(*, uri: str) -> ResolvedBase64DataUrl:
    """Read a base64 data URL into its declared media type and its payload.

    Args:
        uri: A data URL in the format data:{mime};base64,{data}

    Returns:
        ResolvedBase64DataUrl with the media type as the header declares it, parameters included, or `None` when it
        declares none, and the base64 payload.

    Raises:
        DataUrlError: `uri` is not a base64 data URL.
    """
    parsed = parse_base64_data_url(uri=uri)
    return ResolvedBase64DataUrl(
        original=uri,
        mime_type=parsed.media_type or None,
        base64_data=parsed.payload,
    )
