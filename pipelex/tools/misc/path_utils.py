import os
import urllib.parse

from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME
from pipelex.types import StrEnum


class InterpretedPathOrUrl(StrEnum):
    HTTP_URL = "http_url"
    LOCAL_FILE_PATH_URL = "local_file_path_url"
    FILE_NAME = "file_name"
    FILE_PATH = "file_path"
    BASE_64 = "base_64"
    PIPELEX_STORAGE = "pipelex_storage"

    @property
    def desc(self) -> str:
        match self:
            case InterpretedPathOrUrl.HTTP_URL:
                return "HTTP URL"
            case InterpretedPathOrUrl.LOCAL_FILE_PATH_URL:
                return "Local file path URL"
            case InterpretedPathOrUrl.FILE_NAME:
                return "File Name"
            case InterpretedPathOrUrl.FILE_PATH:
                return "File path"
            case InterpretedPathOrUrl.BASE_64:
                return "Base 64"
            case InterpretedPathOrUrl.PIPELEX_STORAGE:
                return "Pipelex Storage"


def interpret_path_or_url(path_or_uri: str) -> InterpretedPathOrUrl:
    """Determines whether a string represents a file URI, URL, file path, or Pipelex storage URI.

    This function analyzes the input string to categorize it as one of several types:

    - Pipelex storage URI (starts with "pipelex-storage://")
    - File URI (starts with "file://")
    - URL (starts with "http")
    - File path (contains OS path separator)
    - File name (anything else)

    Args:
        path_or_uri: The string to interpret, which could be a Pipelex storage URI,
            file URI, URL, or file path.

    Returns:
        InterpretedPathOrUrl: An enum value indicating the type of the input string:

            - PIPELEX_STORAGE for pipelex-storage:// URIs
            - FILE_URI for file:// URIs
            - URL for http(s) URLs
            - FILE_PATH for paths with OS separators
            - FILE_NAME for simple file names
            - BASE_64 for base64-encoded images

    Example:
        >>> interpret_path_or_url("pipelex-storage://images/photo.png")
        InterpretedPathOrUrl.PIPELEX_STORAGE
        >>> interpret_path_or_url("file:///home/user/file.txt")
        InterpretedPathOrUrl.FILE_URI
        >>> interpret_path_or_url("https://example.com")
        InterpretedPathOrUrl.URL
        >>> interpret_path_or_url("/home/user/file.txt")
        InterpretedPathOrUrl.FILE_PATH
    """
    if path_or_uri.startswith(PIPELEX_STORAGE_SCHEME):
        return InterpretedPathOrUrl.PIPELEX_STORAGE
    elif path_or_uri.startswith("file://"):
        return InterpretedPathOrUrl.LOCAL_FILE_PATH_URL
    elif path_or_uri.startswith("http"):
        return InterpretedPathOrUrl.HTTP_URL
    elif os.sep in path_or_uri:
        return InterpretedPathOrUrl.FILE_PATH
    else:
        return InterpretedPathOrUrl.FILE_NAME


def clarify_path_or_url(path_or_uri: str) -> tuple[str | None, str | None]:
    """Separates a path_or_uri string into either a file path or online URL component.

    This function processes the input string to determine its type and returns
    the appropriate components. For file URIs, it converts them to regular file paths.
    Only one of the returned values will be non-None.

    Note:
        For Pipelex storage URIs (pipelex-storage://), use `is_pipelex_storage_uri()`
        to check and `get_storage_provider().load()` to read the content.

    Args:
        path_or_uri: The string to process, which could be a file URI, URL, or file path.

    Returns:
        A tuple containing:

            - file_path: The file path if the input is a file path or URI, None otherwise
            - url: The URL if the input is a URL, None otherwise

    Raises:
        NotImplementedError: If the input is a Base64 string or Pipelex storage URI.

    Example:
        >>> clarify_path_or_url("file:///home/user/file.txt")
        ('/home/user/file.txt', None)
        >>> clarify_path_or_url("https://example.com")
        (None, 'https://example.com')
        >>> clarify_path_or_url("/home/user/file.txt")
        ('/home/user/file.txt', None)
    """
    file_path: str | None
    url: str | None
    match interpret_path_or_url(path_or_uri):
        case InterpretedPathOrUrl.LOCAL_FILE_PATH_URL:
            parsed_uri = urllib.parse.urlparse(path_or_uri)
            file_path = urllib.parse.unquote(parsed_uri.path)
            url = None
        case InterpretedPathOrUrl.HTTP_URL:
            file_path = None
            url = path_or_uri
        case InterpretedPathOrUrl.FILE_PATH:
            # it's a file path
            file_path = path_or_uri
            url = None
        case InterpretedPathOrUrl.FILE_NAME:
            file_path = path_or_uri
            url = None
        case InterpretedPathOrUrl.BASE_64:
            msg = "Base 64 is not supported by clarify_path_or_url"
            raise NotImplementedError(msg)
        case InterpretedPathOrUrl.PIPELEX_STORAGE:
            msg = "Pipelex storage URIs are not supported by clarify_path_or_url; use is_pipelex_storage_uri() and storage_provider.load()"
            raise NotImplementedError(msg)
    return file_path, url


def is_pipelex_storage_uri(path_or_uri: str) -> bool:
    """Check if a string is a Pipelex storage URI.

    Args:
        path_or_uri: The string to check.

    Returns:
        True if the string starts with the Pipelex storage scheme.
    """
    return path_or_uri.startswith(PIPELEX_STORAGE_SCHEME)


def resolve_path_or_url_for_reading(path_or_uri: str) -> str:
    """Resolve a path-or-URI to a single string suitable for file-reading/conversion calls.

    This is a convenience wrapper around `clarify_path_or_url()` that returns a single value:
    - the http(s) URL if `path_or_uri` is a URL
    - otherwise a local file path (including normalized `file://...` URIs)
    """
    file_path, url = clarify_path_or_url(path_or_uri=path_or_uri)
    resolved = url or file_path
    assert resolved is not None
    return resolved
