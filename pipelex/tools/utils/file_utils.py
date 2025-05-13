# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import importlib.resources
import os
import shutil
import urllib.parse
from contextlib import contextmanager
from typing import List, Optional

import requests

from pipelex.tools.utils.path_utils import path_exists


def save_to_path(text_to_save: str, path: str):
    """
    Writes text content to a file at the specified path.

    This function opens a file in write mode and writes the provided text to it.
    If the file already exists, it will be overwritten.

    Args:
        text_to_save (str): The text content to write to the file.
        path (str): The file path where the content should be saved.

    Raises:
        IOError: If there are issues writing to the file (e.g., permission denied).
    """
    with open(path, "w") as file:
        file.write(text_to_save)


def remove_file(file_path: str):
    """
    Removes a file if it exists at the specified path.

    This function checks if a file exists before attempting to remove it,
    preventing errors from trying to remove non-existent files.

    Args:
        file_path (str): The path to the file to be removed.

    Note:
        This function silently succeeds if the file doesn't exist.
    """
    if path_exists(file_path):
        os.remove(file_path)


def remove_folder(folder_path: str) -> None:
    """
    Removes a folder if it exists at the specified path.

    This function checks if a folder exists before attempting to remove it,
    preventing errors from trying to remove non-existent folders.

    Args:
        folder_path (str): The path to the folder to be removed.
    """
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)


@contextmanager
def temp_file(file_path: str, content: str):
    """
    Creates a temporary file with the given content that is automatically removed when the context exits.

    This function is a context manager that creates a file at the specified path with the given content.
    The file is guaranteed to be removed when exiting the context, even if an exception occurs.

    Args:
        file_path (str): The path where the temporary file should be created.
        content (str): The content to write to the temporary file.

    Yields:
        str: The path to the created temporary file.

    Example:
        with temp_file("path/to/temp.txt", "some content") as path:
            # Use the temporary file
            # File will be automatically removed after the with block
    """
    try:
        save_to_path(content, file_path)
        yield file_path
    finally:
        remove_file(file_path)


def load_from_path(path: str) -> str:
    """
    Reads and returns the entire contents of a text file.

    This function opens a file in text mode using UTF-8 encoding and reads
    its entire contents into a string.

    Args:
        path (str): The file path to read from.

    Returns:
        str: The complete contents of the file as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    with open(path, encoding="utf-8") as file:
        return file.read()


def failable_load_from_path(path: str) -> Optional[str]:
    """
    Attempts to read a text file, returning None if the file doesn't exist.

    This function is a safer version of load_from_path that handles missing files
    gracefully by returning None instead of raising an error.

    Args:
        path (str): The file path to read from.

    Returns:
        Optional[str]: The complete contents of the file as a string, or None if the file doesn't exist.
    """
    if not path_exists(path):
        return None
    return load_from_path(path)


def ensure_directory_exists(directory_path: str) -> None:
    """
    Creates a directory and any necessary parent directories if they don't exist.

    Args:
        directory_path (str): The path to the directory to create.
    """
    os.makedirs(directory_path, exist_ok=True)


def copy_file(source_path: str, target_path: str, overwrite: bool = True) -> None:
    """
    Copies a file from the source path to the target path.

    Creates any necessary parent directories for the target path if they don't exist.

    Args:
        source_path (str): The path to the source file.
        target_path (str): The path to the target file.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to True.
    """
    # Ensure the target directory exists
    target_dir = os.path.dirname(target_path)
    if target_dir:
        ensure_directory_exists(target_dir)

    if not os.path.exists(target_path) or overwrite:
        shutil.copy2(source_path, target_path)


def copy_file_from_package(
    package_name: str,
    file_path_in_package: str,
    target_path: str,
    overwrite: bool = True,
) -> None:
    """
    Copies a file from a package to a target directory.
    """
    file_path = str(importlib.resources.files(package_name).joinpath(file_path_in_package))
    copy_file(
        source_path=file_path,
        target_path=target_path,
        overwrite=overwrite,
    )


def copy_folder_from_package(
    package_name: str,
    folder_path_in_package: str,
    target_dir: str,
    overwrite: bool = True,
) -> None:
    """
    Copies a folder from a package to a target directory.

    This function walks through the specified folder in the package and copies
    all files and directories to the target directory, preserving the directory
    structure.

    Args:
        package_name (str): The name of the package to copy from.
        folder_path_in_package (str): The path to the folder in the package to copy.
        target_dir (str): The target directory to copy the folder to.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to True.
    """
    os.makedirs(target_dir, exist_ok=True)

    # Use importlib.resources to get the path to the package resource
    data_dir_str = str(importlib.resources.files(package_name).joinpath(folder_path_in_package))

    copied_files: list[str] = []

    # Walk through all directories and files recursively
    for root, _, files in os.walk(data_dir_str):
        # Create the corresponding subdirectory in the target directory
        rel_path = os.path.relpath(root, data_dir_str)
        target_subdir = os.path.join(target_dir, rel_path) if rel_path != "." else target_dir
        os.makedirs(target_subdir, exist_ok=True)

        # Copy all files in the current directory
        for file in files:
            src_file = os.path.join(root, file)
            dest_file = os.path.join(target_subdir, file)

            # Check if the file exists and respect the overwrite parameter
            if not os.path.exists(dest_file) or overwrite:
                copy_file(
                    source_path=src_file,
                    target_path=dest_file,
                    overwrite=overwrite,
                )
                copied_files.append(dest_file)


def find_folders_by_name(
    base_path: str,
    folder_name: str,
) -> List[str]:
    """
    Find all folders with a specific name within the given base path.

    Args:
        base_path: The starting directory path to search from
        folder_name: The name of the folders to find

    Returns:
        A list of paths to all folders matching the specified name
    """
    folder_paths: List[str] = []

    # Add all subdirectories with the specified name
    for root, dirs, _ in os.walk(base_path):
        for dir_name in dirs:
            if dir_name == folder_name:
                folder_paths.append(os.path.join(root, dir_name))
    return folder_paths


# TODO: Implement this
def get_local_file_type_from_content(path: str):
    "Use file content to determine the type when no extension is provided in the path/filename"
    pass


def get_local_type_from_path(path: str) -> str:
    _, extension = os.path.splitext(path)
    extension = extension.lower()
    return extension


def get_remote_file_type_from_url(url: str) -> str:
    parsed_url = urllib.parse.urlparse(url)
    path = parsed_url.path
    _, extension = os.path.splitext(path)
    extension = extension.lower()
    return extension


def get_remote_file_type_from_content(url: str) -> str:
    response = requests.head(url, timeout=5)
    content_type = response.headers.get("Content-Type", "").lower()
    return content_type
