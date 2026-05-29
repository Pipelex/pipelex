import filecmp
import importlib.resources
import os
import shutil
from pathlib import Path

import aiofiles
from pydantic import BaseModel, ConfigDict, Field

MAX_FILE_PATH_LENGTH = 4096

########################################################
# Save & Load
########################################################


def save_bytes_to_binary_file(file_path: Path, byte_data: bytes, create_directory: bool = False) -> Path:
    """Write binary data to a file.

    Args:
        file_path (Path): Path where the binary data will be saved
        byte_data (bytes): Binary data to be written
        create_directory (bool, optional): Whether to create the directory if it doesn't exist.
            Defaults to False.

    Returns:
        Path: Path to the saved file

    """
    # Ensure the directory exists
    if create_directory:
        ensure_directory_exists(file_path.parent)

    file_path.write_bytes(byte_data)
    return file_path


def save_text_to_path(text: str, path: Path, create_directory: bool = False):
    """Writes text content to a file at the specified path.

    This function opens a file in write mode and writes the provided text to it.
    If the file already exists, it will be overwritten.

    Args:
        text (str): The text content to write to the file.
        path (Path): The file path where the content should be saved.
        create_directory (bool, optional): Whether to create the directory if it doesn't exist.
            Defaults to False.

    Raises:
        IOError: If there are issues writing to the file (e.g., permission denied).

    """
    if create_directory:
        directory = path.parent
        ensure_directory_exists(directory)

    path.write_text(text, encoding="utf-8")


def load_text_from_path(path: Path) -> str:
    """Reads and returns the entire contents of a text file.

    This function opens a file in text mode using UTF-8 encoding and reads
    its entire contents into a string.

    Args:
        path (Path): The file path to read from.

    Returns:
        str: The complete contents of the file as a string.

    Raises:
        FileNotFoundError: If the file does not exist.

    """
    return path.read_text(encoding="utf-8")


def failable_load_text_from_path(path: Path) -> str | None:
    """Attempts to read a text file, returning None if the file doesn't exist.

    This function is a safer version of load_text_from_path that handles missing files
    gracefully by returning None instead of raising an error.

    Args:
        path (Path): The file path to read from.

    Returns:
        Optional[str]: The complete contents of the file as a string, or None if the file doesn't exist.

    """
    if not path.exists():
        return None
    return load_text_from_path(path)


def load_binary(path: Path) -> bytes:
    return path.read_bytes()


async def load_binary_async(path: Path) -> bytes:
    async with aiofiles.open(path, "rb") as fp:  # pyright: ignore[reportUnknownMemberType]
        return await fp.read()


########################################################
# Copy & Remove
########################################################


def copy_file(source_path: Path, target_path: Path, overwrite: bool = True) -> None:
    """Copies a file from the source path to the target path.

    Creates any necessary parent directories for the target path if they don't exist.

    Args:
        source_path (Path): The path to the source file.
        target_path (Path): The path to the target file.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to True.

    """
    # Ensure the target directory exists
    ensure_directory_exists(target_path.parent)

    if not target_path.exists() or overwrite:
        shutil.copy2(source_path, target_path)


def copy_file_from_package(
    package_name: str,
    file_path_in_package: str,
    target_path: Path,
    overwrite: bool = True,
) -> None:
    """Copies a file from a package to a target directory."""
    file_path = Path(str(importlib.resources.files(package_name).joinpath(file_path_in_package)))
    copy_file(
        source_path=file_path,
        target_path=target_path,
        overwrite=overwrite,
    )


def copy_folder_from_package(
    package_name: str,
    folder_path_in_package: str,
    target_dir: Path,
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
        target_dir (Path): The target directory to copy the folder to.
        overwrite (bool, optional): Whether to overwrite existing files. Defaults to True.
        non_overwrite_files (Optional[List[str]], optional): List of files to not overwrite. Defaults to None.

    """
    target_dir.mkdir(parents=True, exist_ok=True)

    # Use importlib.resources to get the path to the package resource
    data_dir = Path(str(importlib.resources.files(package_name).joinpath(folder_path_in_package)))

    copied_files: list[Path] = []

    if non_overwrite_files is None:
        non_overwrite_files = []

    # Walk through all directories and files recursively
    for source_path in data_dir.rglob("*"):
        if not source_path.is_file():
            continue
        relative_path = source_path.relative_to(data_dir)
        dest_file = target_dir / relative_path
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # Check if the file exists and respect the overwrite parameter
        if not dest_file.exists() or (overwrite and source_path.name not in non_overwrite_files):
            copy_file(
                source_path=source_path,
                target_path=dest_file,
                overwrite=overwrite,
            )
            copied_files.append(dest_file)


def remove_file(file_path: Path):
    """Removes a file if it exists at the specified path.

    This function checks if a file exists before attempting to remove it,
    preventing errors from trying to remove non-existent files.

    Args:
        file_path (Path): The path to the file to be removed.

    Note:
        This function silently succeeds if the file doesn't exist.

    """
    if file_path.exists():
        file_path.unlink()


def remove_folder(folder_path: Path) -> None:
    """Removes a folder if it exists at the specified path.

    This function checks if a folder exists before attempting to remove it,
    preventing errors from trying to remove non-existent folders.

    Args:
        folder_path (Path): The path to the folder to be removed.

    """
    if folder_path.exists():
        shutil.rmtree(folder_path)


class MirrorDirResult(BaseModel):
    """Outcome of a mirror_dir operation.

    Paths are relative to the target directory, in POSIX form, and sorted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    copied_files: list[str] = Field(default_factory=list)
    created_dirs: list[str] = Field(default_factory=list)
    deleted_files: list[str] = Field(default_factory=list)
    deleted_dirs: list[str] = Field(default_factory=list)
    dry_run: bool = False

    @property
    def change_count(self) -> int:
        """Total number of files copied, directories created, and files and directories deleted."""
        return len(self.copied_files) + len(self.created_dirs) + len(self.deleted_files) + len(self.deleted_dirs)

    @property
    def has_changes(self) -> bool:
        """Whether the mirror operation copied or deleted anything."""
        return self.change_count > 0


def _reraise_walk_error(walk_error: OSError) -> None:
    """Re-raise errors from os.walk so mirror_dir fails loudly instead of silently skipping."""
    raise walk_error


def mirror_dir(
    source_dir: Path,
    target_dir: Path,
    exclude_files: frozenset[str] | None = None,
    exclude_dirs: frozenset[str] | None = None,
    dry_run: bool = False,
) -> MirrorDirResult:
    """Mirrors a source directory onto a target directory (recursive copy + delete).

    Recursively copies files that are new or whose content differs, and deletes
    files and directories present in the target but absent from the source.
    Excluded files and directories are matched by basename and skipped for both
    copying and deletion, so an excluded entry that exists only on the target
    side is preserved. Operates on regular files and directories only; symlinks
    are not specially preserved.

    Args:
        source_dir (Path): The reference directory to mirror from. Must exist.
        target_dir (Path): The directory brought in sync. Created if missing.
        exclude_files (frozenset[str] | None): File basenames to skip entirely.
        exclude_dirs (frozenset[str] | None): Directory basenames to skip entirely.
        dry_run (bool): If True, report changes without touching the filesystem.

    Returns:
        MirrorDirResult: The files copied, directories created, and files and
        directories deleted, with paths relative to the target directory.

    Raises:
        FileNotFoundError: If source_dir does not exist.
        NotADirectoryError: If source_dir exists but is not a directory.
        OSError: If the filesystem walk or a copy/delete operation fails.
    """
    source_root = Path(source_dir)
    target_root = Path(target_dir)
    excluded_files = exclude_files or frozenset()
    excluded_dirs = exclude_dirs or frozenset()

    # Validate the source before Pass 1: an invalid source makes every
    # is_dir()/is_file() probe return false, which would delete the entire
    # target tree before Pass 2's walk gets a chance to fail.
    if not source_root.exists():
        msg = f"mirror_dir source directory does not exist: {source_root}"
        raise FileNotFoundError(msg)
    if not source_root.is_dir():
        msg = f"mirror_dir source path is not a directory: {source_root}"
        raise NotADirectoryError(msg)

    deleted_files: list[str] = []
    deleted_dirs: list[str] = []
    created_dirs: list[str] = []
    copied_files: list[str] = []

    # Pass 1: delete target entries absent from the source. Done before the copy
    # pass so a name that flips between file and directory is cleared first.
    if target_root.exists():
        for current_root, dir_names, file_names in os.walk(target_root, topdown=True, onerror=_reraise_walk_error):
            relative_root = Path(current_root).relative_to(target_root)
            kept_dir_names: list[str] = []
            for dir_name in sorted(dir_names):
                if dir_name in excluded_dirs:
                    continue
                if (source_root / relative_root / dir_name).is_dir():
                    kept_dir_names.append(dir_name)
                    continue
                deleted_dirs.append((relative_root / dir_name).as_posix())
                if not dry_run:
                    dir_to_remove = Path(current_root) / dir_name
                    # shutil.rmtree raises on directory symlinks; unlink them instead.
                    if dir_to_remove.is_symlink():
                        dir_to_remove.unlink()
                    else:
                        remove_folder(dir_to_remove)
            dir_names[:] = kept_dir_names
            for file_name in sorted(file_names):
                if file_name in excluded_files:
                    continue
                if (source_root / relative_root / file_name).is_file():
                    continue
                deleted_files.append((relative_root / file_name).as_posix())
                if not dry_run:
                    # ``unlink(missing_ok=True)`` removes the entry by name regardless of
                    # whether the target exists, so a broken symlink (which makes
                    # ``Path.exists()`` return ``False``) is still cleared from the mirror.
                    (Path(current_root) / file_name).unlink(missing_ok=True)

    # Pass 2: copy new or changed files from the source into the target.
    for current_root, dir_names, file_names in os.walk(source_root, topdown=True, onerror=_reraise_walk_error):
        dir_names[:] = sorted(dir_name for dir_name in dir_names if dir_name not in excluded_dirs)
        relative_root = Path(current_root).relative_to(source_root)
        target_subdir = target_root / relative_root
        # Record directories created in the target so an added empty directory
        # still counts as a change (and a dry run reports it accurately).
        if relative_root.parts and not target_subdir.is_dir():
            created_dirs.append(relative_root.as_posix())
        if not dry_run:
            ensure_directory_exists(target_subdir)
        for file_name in sorted(file_names):
            if file_name in excluded_files:
                continue
            source_file = Path(current_root) / file_name
            target_file = target_root / relative_root / file_name
            # A target symlink must be replaced by the real source file, not written
            # through: copy_file() would otherwise overwrite whatever the link points
            # to, leaving the mirror tree in the wrong shape.
            if target_file.is_symlink():
                if not dry_run:
                    target_file.unlink()
            elif target_file.is_file() and filecmp.cmp(str(source_file), str(target_file), shallow=False):
                continue
            if not dry_run:
                copy_file(source_path=source_file, target_path=target_file)
            copied_files.append((relative_root / file_name).as_posix())

    return MirrorDirResult(
        copied_files=sorted(copied_files),
        created_dirs=sorted(created_dirs),
        deleted_files=sorted(deleted_files),
        deleted_dirs=sorted(deleted_dirs),
        dry_run=dry_run,
    )


########################################################
# Check & get paths
########################################################


def ensure_directory_exists(directory_path: Path) -> None:
    """Creates a directory and any necessary parent directories if they don't exist.

    Args:
        directory_path (Path): The path to the directory to create.

    """
    directory_path.mkdir(parents=True, exist_ok=True)


def ensure_path(path: Path) -> bool:
    """Ensures a directory exists at the specified path, creating it if necessary.

    This function checks if a directory exists at the given path. If it doesn't exist,
    it creates the directory and any necessary parent directories.

    Args:
        path (Path): The path where the directory should exist.

    Returns:
        bool: True if the directory was created, False if it already existed.

    """
    if path.exists():
        return False
    path.mkdir(parents=True, exist_ok=True)
    return True


def ensure_directory_for_file_path(file_path: Path) -> None:
    """Ensures a directory exists for the specified file path.

    Args:
        file_path (Path): The path to the file.
    """
    ensure_directory_exists(file_path.parent)


def path_exists(path_str: str | Path) -> bool:
    """Checks if a file or directory exists at the specified path.

    This function converts the input string path to a Path object and checks
    if anything exists at that location in the filesystem.

    Args:
        path_str (str): The path to check for existence.

    Returns:
        bool: True if a file or directory exists at the path, False otherwise.

    """
    return Path(path_str).exists()


def get_incremental_directory_path(base_path: Path, base_name: str, start_at: int = 1) -> Path:
    """Generates a unique directory path by incrementing a counter until an unused path is found.

    This function creates a directory path in the format 'base_path/base_name_XX' where XX
    is a two-digit number that starts at start_at and increments until an unused path is found.
    The directory is then created at this path.

    Args:
        base_path (Path): The parent directory where the new directory will be created.
        base_name (str): The base name for the directory (will be appended with _XX).
        start_at (int, optional): The number to start counting from. Defaults to 1.

    Returns:
        Path: The path to the newly created directory.

    """
    counter = start_at
    while True:
        tested_path = base_path / f"{base_name}_{counter:02d}"
        if not tested_path.exists():
            break
        counter += 1
    ensure_path(tested_path)
    return tested_path


def get_incremental_file_path(
    base_path: Path,
    base_name: str,
    extension: str,
    start_at: int = 1,
    avoid_suffix_if_possible: bool = False,
) -> Path:
    """Generates a unique file path by incrementing a counter until an unused path is found.

    This function creates a file path in the format 'base_path/base_name_XX.extension' where XX
    is a two-digit number that starts at start_at and increments until an unused path is found.
    Unlike get_incremental_directory_path, this function only generates the path and does not create the file.

    Args:
        base_path (Path): The directory where the file path will be generated.
        base_name (str): The base name for the file (will be appended with _XX).
        extension (str): The file extension (without the dot).
        start_at (int, optional): The number to start counting from. Defaults to 1.
        avoid_suffix_if_possible (bool, optional): If True, avoids adding a suffix if possible. Defaults to False.

    Returns:
        Path: A unique file path that does not exist in the filesystem.

    """
    if avoid_suffix_if_possible:
        # try without adding the suffix
        tested_path = base_path / f"{base_name}.{extension}"
        if not tested_path.exists():
            return tested_path

    # we must add a number to the base name
    counter = start_at
    while True:
        tested_path = base_path / f"{base_name}_{counter:02d}.{extension}"
        if not tested_path.exists():
            break
        counter += 1
    return tested_path


########################################################
# Find files
########################################################


def find_files_in_dir(
    dir_path: Path,
    pattern: str,
    is_recursive: bool = True,
    excluded_dirs: list[str] | None = None,
    force_include_dirs: list[str] | None = None,
) -> list[Path]:
    """Find files matching a pattern in a directory.

    Args:
        dir_path: Directory path to search in
        pattern: File pattern to match (e.g. "*.py")
        is_recursive: Whether to search recursively in subdirectories
        excluded_dirs: List of directory names to exclude from the search (e.g. [".venv", "node_modules"])
        force_include_dirs: List of directories to force include even if they are within excluded_dirs.
                           Can be either full absolute paths or directory names.

    Returns:
        List of matching Path objects

    """
    path = dir_path
    files: list[Path] = []
    filtered_files: list[Path] = []
    # Sort results for consistent ordering across platforms and Python versions.
    # Python < 3.13 returns rglob/glob results in filesystem order, which varies
    # between macOS (APFS, always sorted) and Linux (ext4, inode order).
    if is_recursive:
        files = sorted(path.rglob(pattern))
    else:
        files = sorted(path.glob(pattern))
    for file in files:
        # Check if file is under any excluded directory
        is_excluded = False
        if excluded_dirs is not None:
            for excluded_dir in excluded_dirs:
                excluded_path = Path(excluded_dir)
                # If excluded_dir is an absolute path, check if file is under it
                if excluded_path.is_absolute():
                    try:
                        # Resolve both paths to handle symlinks (e.g., /var -> /private/var on macOS)
                        file.resolve().relative_to(excluded_path.resolve())
                        is_excluded = True
                        break
                    except ValueError:
                        # file is not relative to excluded_path
                        continue
                # If excluded_dir is just a directory name, check if it's in the file path parts
                elif excluded_dir in file.parts:
                    is_excluded = True
                    break

        # Check if file is in a force include directory (forced inclusion despite exclusions)
        # Force include dirs can be full paths or directory names
        should_force_include = False
        if force_include_dirs is not None:
            for force_include_dir in force_include_dirs:
                force_include_path = Path(force_include_dir)
                # If force_include_dir is an absolute path, check if file is under it
                if force_include_path.is_absolute():
                    try:
                        file.relative_to(force_include_path)
                        should_force_include = True
                        break
                    except ValueError:
                        # file is not relative to force_include_path
                        continue
                # If force_include_dir is just a directory name, check if it's in the file path parts
                elif force_include_dir in file.parts:
                    should_force_include = True
                    break

        # Include if not excluded, or if force included
        if not is_excluded or should_force_include:
            filtered_files.append(file)

    return filtered_files
