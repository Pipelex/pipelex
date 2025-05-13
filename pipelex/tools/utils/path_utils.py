# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import os
import urllib.parse
from enum import StrEnum
from pathlib import Path
from typing import List, Optional, Tuple


def ensure_path(path: str) -> bool:
    """
    Ensures a directory exists at the specified path, creating it if necessary.

    This function checks if a directory exists at the given path. If it doesn't exist,
    it creates the directory and any necessary parent directories.

    Args:
        path (str): The path where the directory should exist.

    Returns:
        bool: True if the directory was created, False if it already existed.
    """
    typed_path = Path(path)
    if typed_path.exists():
        return False
    typed_path.mkdir(parents=True, exist_ok=True)
    return True


def path_exists(path_str: str) -> bool:
    """
    Checks if a file or directory exists at the specified path.

    This function converts the input string path to a Path object and checks
    if anything exists at that location in the filesystem.

    Args:
        path_str (str): The path to check for existence.

    Returns:
        bool: True if a file or directory exists at the path, False otherwise.
    """
    path = Path(path_str)
    return path.exists()


def get_incremental_directory_path(base_path: str, base_name: str, start_at: int = 1) -> str:
    """
    Generates a unique directory path by incrementing a counter until an unused path is found.

    This function creates a directory path in the format 'base_path/base_name_XX' where XX
    is a two-digit number that starts at start_at and increments until an unused path is found.
    The directory is then created at this path.

    Args:
        base_path (str): The parent directory where the new directory will be created.
        base_name (str): The base name for the directory (will be appended with _XX).
        start_at (int, optional): The number to start counting from. Defaults to 1.

    Returns:
        str: The path to the newly created directory.
    """
    counter = start_at
    while True:
        tested_path = f"{base_path}/{base_name}_%02d" % counter
        if not path_exists(tested_path):
            break
        counter += 1
    ensure_path(tested_path)
    return tested_path


def get_incremental_file_path(base_path: str, base_name: str, extension: str, start_at: int = 1) -> str:
    """
    Generates a unique file path by incrementing a counter until an unused path is found.

    This function creates a file path in the format 'base_path/base_name_XX.extension' where XX
    is a two-digit number that starts at start_at and increments until an unused path is found.
    Unlike get_incremental_directory_path, this function only generates the path and does not create the file.

    Args:
        base_path (str): The directory where the file path will be generated.
        base_name (str): The base name for the file (will be appended with _XX).
        extension (str): The file extension (without the dot).
        start_at (int, optional): The number to start counting from. Defaults to 1.

    Returns:
        str: A unique file path that does not exist in the filesystem.
    """
    counter = start_at
    while True:
        tested_path = f"{base_path}/{base_name}_%02d.{extension}" % counter
        if not path_exists(tested_path):
            break
        counter += 1
    return tested_path


class InterpretedPathOrUrl(StrEnum):
    FILE_URI = "file_uri"
    FILE_PATH = "file_path"
    URL = "url"

    @property
    def desc(self) -> str:
        match self:
            case InterpretedPathOrUrl.FILE_URI:
                return "File URI"
            case InterpretedPathOrUrl.FILE_PATH:
                return "File Path"
            case InterpretedPathOrUrl.URL:
                return "URL"


def interpret_path_or_url(path_or_url: str) -> InterpretedPathOrUrl:
    """
    Determines whether a string represents a file URI, URL, or file path.

    This function analyzes the input string to categorize it as one of three types:
    - File URI (starts with "file://")
    - URL (starts with "http")
    - File path (anything else)

    Args:
        path_or_url (str): The string to interpret, which could be a file URI,
            URL, or file path.

    Returns:
        InterpretedPathOrUrl: An enum value indicating the type of the input string:
            - FILE_URI for file:// URIs
            - URL for http(s) URLs
            - FILE_PATH for everything else

    Example:
        >>> interpret_path_or_url("file:///home/user/file.txt")
        InterpretedPathOrUrl.FILE_URI
        >>> interpret_path_or_url("https://example.com")
        InterpretedPathOrUrl.URL
        >>> interpret_path_or_url("/home/user/file.txt")
        InterpretedPathOrUrl.FILE_PATH
    """
    if path_or_url.startswith("file://"):
        return InterpretedPathOrUrl.FILE_URI
    elif path_or_url.startswith("http"):
        return InterpretedPathOrUrl.URL
    else:
        return InterpretedPathOrUrl.FILE_PATH


def clarify_path_or_url(path_or_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Separates a path-or-URL string into either a file path or URL component.

    This function processes the input string to determine its type and returns
    the appropriate components. For file URIs, it converts them to regular file paths.
    Only one of the returned values will be non-None.

    Args:
        path_or_url (str): The string to process, which could be a file URI,
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
    match interpret_path_or_url(path_or_url):
        case InterpretedPathOrUrl.FILE_URI:
            parsed_uri = urllib.parse.urlparse(path_or_url)
            file_path = urllib.parse.unquote(parsed_uri.path)
            url = None
        case InterpretedPathOrUrl.URL:
            file_path = None
            url = path_or_url
        case InterpretedPathOrUrl.FILE_PATH:
            # it's a file path
            file_path = path_or_url
            url = None
    return file_path, url


def folder_path_exists(folder_path: str) -> None:
    """Validates that the folder path exists and is a directory."""
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Folder '{folder_path}' does not exist")

    if not os.path.isdir(folder_path):
        raise NotADirectoryError(f"Path '{folder_path}' is not a directory")


def find_files_in_dir(dir_path: str, pattern: str, is_recursive: bool) -> List[Path]:
    """
    Find files matching a pattern in a directory.

    Args:
        dir_path: Directory path to search in
        pattern: File pattern to match (e.g. "*.py")
        recursive: Whether to search recursively in subdirectories

    Returns:
        List of matching Path objects
    """
    path = Path(dir_path)
    if is_recursive:
        return list(path.rglob(pattern))
    else:
        return list(path.glob(pattern))
