import os
import urllib.parse
from typing import Optional, Tuple

from pipelex.types import StrEnum


class InterpretedPathOrUrl(StrEnum):
    FILE_URI = "file_uri"
    FILE_PATH = "file_path"
    URL = "uri"
    FILE_NAME = "file_name"
    BASE_64 = "base_64"

    @property
    def desc(self) -> str:
        match self:
            case InterpretedPathOrUrl.FILE_URI:
                return "File URI"
            case InterpretedPathOrUrl.FILE_PATH:
                return "File Path"
            case InterpretedPathOrUrl.URL:
                return "URL"
            case InterpretedPathOrUrl.FILE_NAME:
                return "File Name"
            case InterpretedPathOrUrl.BASE_64:
                return "Base 64"


def interpret_path_or_url(path_or_uri: str) -> InterpretedPathOrUrl:
    """
    Determines whether a string represents a file URI, URL, or file path.

    This function analyzes the input string to categorize it as one of three types:
    - File URI (starts with "file://")
    - URL (starts with "http")
    - File path (anything else)

    Args:
        path_or_uri (str): The string to interpret, which could be a file URI,
            URL, or file path.

    Returns:
        InterpretedPathOrUrl: An enum value indicating the type of the input string:
            - FILE_URI for file:// URIs
            - FILE_PATH for everything else
            - URL for http(s) URLs
            - FILE_NAME for file names
            - BASE_64 for base64-encoded images

    Example:
        >>> interpret_path_or_url("file:///home/user/file.txt")
        InterpretedPathOrUrl.FILE_URI
        >>> interpret_path_or_url("https://example.com")
        InterpretedPathOrUrl.URL
        >>> interpret_path_or_url("/home/user/file.txt")
        InterpretedPathOrUrl.FILE_PATH
    """
    if path_or_uri.startswith("file://"):
        return InterpretedPathOrUrl.FILE_URI
    elif path_or_uri.startswith("http"):
        return InterpretedPathOrUrl.URL
    elif os.sep in path_or_uri:
        return InterpretedPathOrUrl.FILE_PATH
    else:
        return InterpretedPathOrUrl.FILE_NAME


def clarify_path_or_url(path_or_uri: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Separates a path_or_uri string into either a file path or online URL component.

    This function processes the input string to determine its type and returns
    the appropriate components. For file URIs, it converts them to regular file paths.
    Only one of the returned values will be non-None.

    Args:
        path_or_uri (str): The string to process, which could be a file URI,
            URL, or file path.

    Returns:
        Tuple[Optional[str], Optional[str]]: A tuple containing:
            - file_path: The file path if the input is a file path or URI, None otherwise
            - url: The URL if the input is a URL, None otherwise

    Example:
        >>> clarify_path_or_url("file:///home/user/file.txt")
        ('/home/user/file.txt', None)
        >>> clarify_path_or_url("https://example.com")
        (None, 'https://example.com')
        >>> clarify_path_or_url("/home/user/file.txt")
        ('/home/user/file.txt', None)
    """
    file_path: Optional[str]
    url: Optional[str]
    match interpret_path_or_url(path_or_uri):
        case InterpretedPathOrUrl.FILE_URI:
            parsed_uri = urllib.parse.urlparse(path_or_uri)
            file_path = urllib.parse.unquote(parsed_uri.path)
            url = None
        case InterpretedPathOrUrl.URL:
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
            raise NotImplementedError("Base 64 is not supported yet by clarify_path_or_url")
    return file_path, url
