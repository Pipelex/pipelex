import importlib.resources
import os
import shutil
from pathlib import Path

########################################################
# Save & Load
########################################################


def save_bytes_to_binary_file(file_path: str, byte_data: bytes, create_directory: bool = False) -> str:
    """Write binary data to a file.

    Args:
        file_path (str): Path where the binary data will be saved
        byte_data (bytes): Binary data to be written
        create_directory (bool, optional): Whether to create the directory if it doesn't exist.
            Defaults to False.

    Returns:
        str: Path to the saved file

    """
    # Ensure the directory exists
    if create_directory:
        ensure_directory_exists(os.path.dirname(file_path))

    with open(file_path, "wb") as f:
        f.write(byte_data)
    return file_path


def save_text_to_path(text: str, path: str, create_directory: bool = False):
    """Writes text content to a file at the specified path.

    This function opens a file in write mode and writes the provided text to it.
    If the file already exists, it will be overwritten.

    Args:
        text (str): The text content to write to the file.
        path (str): The file path where the content should be saved.
        create_directory (bool, optional): Whether to create the directory if it doesn't exist.
            Defaults to False.

    Raises:
        IOError: If there are issues writing to the file (e.g., permission denied).

    """
    if create_directory:
        directory = os.path.dirname(path)
        if directory:
            ensure_directory_exists(directory)

    with open(path, "w", encoding="utf-8") as file:
        file.write(text)


def load_text_from_path(path: str) -> str:
    """Reads and returns the entire contents of a text file.

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


def failable_load_text_from_path(path: str) -> str | None:
    """Attempts to read a text file, returning None if the file doesn't exist.

    This function is a safer version of load_text_from_path that handles missing files
    gracefully by returning None instead of raising an error.

    Args:
        path (str): The file path to read from.

    Returns:
        Optional[str]: The complete contents of the file as a string, or None if the file doesn't exist.

    """
    if not path_exists(path):
        return None
    return load_text_from_path(path)


########################################################
# Copy & Remove
########################################################


def copy_file(source_path: str, target_path: str, overwrite: bool = True) -> None:
    """Copies a file from the source path to the target path.

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
    """Copies a file from a package to a target directory."""
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
    non_overwrite_files: list[str] | None = None,
) -> None:
    """Copies a folder from a package to a target directory.

    This function walks through the specified folder in the package and copies
    all files and directories to the target directory, preserving the directory
    structure.

    Args:
        package_name (str): The name of the package to copy from.
        folder_path_in_package (str): The path to the folder in the package to copy.
        target_dir (str): The target directory to copy the folder to.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to True.
        non_overwrite_files (Optional[List[str]], optional): List of files to not overwrite. Defaults to None.

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

        if non_overwrite_files is None:
            non_overwrite_files = []

        # Copy all files in the current directory
        for file in files:
            src_file = os.path.join(root, file)
            dest_file = os.path.join(target_subdir, file)

            # Check if the file exists and respect the overwrite parameter
            if not Path(dest_file).exists() or (overwrite and file not in non_overwrite_files):
                copy_file(
                    source_path=src_file,
                    target_path=dest_file,
                    overwrite=overwrite,
                )
                copied_files.append(dest_file)


def remove_file(file_path: str):
    """Removes a file if it exists at the specified path.

    This function checks if a file exists before attempting to remove it,
    preventing errors from trying to remove non-existent files.

    Args:
        file_path (str): The path to the file to be removed.

    Note:
        This function silently succeeds if the file doesn't exist.

    """
    if path_exists(file_path):
        Path(file_path).unlink()


def remove_folder(folder_path: str) -> None:
    """Removes a folder if it exists at the specified path.

    This function checks if a folder exists before attempting to remove it,
    preventing errors from trying to remove non-existent folders.

    Args:
        folder_path (str): The path to the folder to be removed.

    """
    if Path(folder_path).exists():
        shutil.rmtree(folder_path)


########################################################
# Check & get paths
########################################################


def ensure_directory_exists(directory_path: str) -> None:
    """Creates a directory and any necessary parent directories if they don't exist.

    Args:
        directory_path (str): The path to the directory to create.

    """
    Path(directory_path).mkdir(parents=True, exist_ok=True)


def ensure_path(path: str) -> bool:
    """Ensures a directory exists at the specified path, creating it if necessary.

    This function checks if a directory exists at the given path. If it doesn't exist,
    it creates the directory and any necessary parent directories.

    Args:
        path (str): The path where the directory should exist.

    Returns:
        bool: True if the directory was created, False if it already existed.

    """
    if Path(path).exists():
        return False
    Path(path).mkdir(parents=True, exist_ok=True)
    return True


def ensure_directory_for_file_path(file_path: str) -> None:
    """Ensures a directory exists for the specified file path.

    Args:
        file_path (str): The path to the file.
    """
    ensure_directory_exists(os.path.dirname(file_path))


def path_exists(path_str: str) -> bool:
    """Checks if a file or directory exists at the specified path.

    This function converts the input string path to a Path object and checks
    if anything exists at that location in the filesystem.

    Args:
        path_str (str): The path to check for existence.

    Returns:
        bool: True if a file or directory exists at the path, False otherwise.

    """
    return Path(path_str).exists()


def get_incremental_directory_path(base_path: str, base_name: str, start_at: int = 1) -> str:
    """Generates a unique directory path by incrementing a counter until an unused path is found.

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


def get_incremental_file_path(
    base_path: str,
    base_name: str,
    extension: str,
    start_at: int = 1,
    avoid_suffix_if_possible: bool = False,
) -> str:
    """Generates a unique file path by incrementing a counter until an unused path is found.

    This function creates a file path in the format 'base_path/base_name_XX.extension' where XX
    is a two-digit number that starts at start_at and increments until an unused path is found.
    Unlike get_incremental_directory_path, this function only generates the path and does not create the file.

    Args:
        base_path (str): The directory where the file path will be generated.
        base_name (str): The base name for the file (will be appended with _XX).
        extension (str): The file extension (without the dot).
        start_at (int, optional): The number to start counting from. Defaults to 1.
        avoid_suffix_if_possible (bool, optional): If True, avoids adding a suffix if possible. Defaults to False.

    Returns:
        str: A unique file path that does not exist in the filesystem.

    """
    if avoid_suffix_if_possible:
        # try without adding the suffix
        tested_path = f"{base_path}/{base_name}.{extension}"
        if not path_exists(tested_path):
            return tested_path

    # we must add a number to the base name
    counter = start_at
    while True:
        tested_path = f"{base_path}/{base_name}_%02d.{extension}" % counter
        if not path_exists(tested_path):
            break
        counter += 1
    return tested_path


########################################################
# Find files
########################################################


def find_files_in_dir(dir_path: str, pattern: str, is_recursive: bool) -> list[Path]:
    """Find files matching a pattern in a directory.

    Args:
        dir_path: Directory path to search in
        pattern: File pattern to match (e.g. "*.py")
        is_recursive: Whether to search recursively in subdirectories

    Returns:
        List of matching Path objects

    """
    path = Path(dir_path)
    if is_recursive:
        return list(path.rglob(pattern))
    return list(path.glob(pattern))
