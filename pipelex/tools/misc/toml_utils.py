from __future__ import annotations

from typing import Any

import tomli
import tomlkit

from pipelex.system.exceptions import ToolError
from pipelex.tools.misc.file_utils import path_exists
from pipelex.tools.misc.json_utils import deep_update


class TomlError(ToolError):
    def __init__(self, message: str, doc: str, pos: int, lineno: int, colno: int):
        super().__init__(message)
        self.doc = doc
        self.pos = pos
        self.lineno = lineno
        self.colno = colno

    @classmethod
    def from_tomli_error(cls, exc: tomli.TOMLDecodeError) -> TomlError:
        return cls(message=exc.msg, doc=exc.doc, pos=exc.pos, lineno=exc.lineno, colno=exc.colno)


def load_toml_from_content(content: str) -> dict[str, Any]:
    """Load TOML from content."""
    try:
        return tomli.loads(content)
    except tomli.TOMLDecodeError as exc:
        raise TomlError.from_tomli_error(exc) from exc


def load_toml_from_path(path: str) -> dict[str, Any]:
    """Load TOML from path.

    Args:
        path: Path to the TOML file

    Returns:
        Dictionary loaded from TOML

    Raises:
        toml.TomlDecodeError: If TOML parsing fails, with file path included

    """
    try:
        with open(path, "rb") as file:
            return tomli.load(file)
    except tomli.TOMLDecodeError as exc:
        msg = f"TOML parsing error in file '{path}': {exc.msg}"
        raise TomlError(message=msg, doc=exc.doc, pos=exc.pos, lineno=exc.lineno, colno=exc.colno) from exc


def load_toml_from_path_if_exists(path: str) -> dict[str, Any] | None:
    """Load TOML from path if it exists."""
    if not path_exists(path):
        return None
    return load_toml_from_path(path)


def load_toml_with_tomlkit(path: str) -> tomlkit.TOMLDocument:
    """Load TOML using tomlkit to preserve formatting and comments.

    Args:
        path: Path to the TOML file

    Returns:
        TOMLDocument that preserves formatting and comments

    """
    with open(path, encoding="utf-8") as file:
        return tomlkit.load(file)


def save_toml_to_path(data: dict[str, Any] | tomlkit.TOMLDocument, path: str) -> None:
    """Save dictionary as TOML to path, preserving formatting and comments.

    Args:
        data: Dictionary or TOMLDocument to save as TOML
        path: Path where the TOML file should be saved

    """
    with open(path, "w", encoding="utf-8") as file:
        tomlkit.dump(data, file)  # type: ignore[arg-type]


def load_toml_from_path_and_merge_with_overrides(paths: list[str]) -> dict[str, Any]:
    """Load and merge toml files from paths if they exist, merged in sequence.

    Returns:
        dict[str, Any]: The merged dictionary
    """
    merged_dict: dict[str, Any] = {}
    for path in paths:
        if one_dict := load_toml_from_path_if_exists(path):
            deep_update(merged_dict, one_dict)

    return merged_dict
