from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

import tomli
import tomlkit

from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.file_utils import path_exists, reject_bare_str_or_path
from pipelex.tools.misc.json_utils import deep_update


def load_toml_from_content(content: str) -> dict[str, Any]:
    """Load TOML from content."""
    try:
        return tomli.loads(content)
    except tomli.TOMLDecodeError as exc:
        raise TomlError.from_tomli_error(exc) from exc


def load_toml_from_path(path: str | Path) -> dict[str, Any]:
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


def load_toml_from_path_if_exists(path: str | Path) -> dict[str, Any] | None:
    """Load TOML from path if it exists."""
    if not path_exists(path):
        return None
    return load_toml_from_path(path)


def load_toml_with_tomlkit(path: str | Path) -> tomlkit.TOMLDocument:
    """Load TOML using tomlkit to preserve formatting and comments.

    Args:
        path: Path to the TOML file

    Returns:
        TOMLDocument that preserves formatting and comments

    """
    with open(path, encoding="utf-8") as file:
        return tomlkit.load(file)


def save_toml_to_path(data: dict[str, Any] | tomlkit.TOMLDocument, *, path: str | Path) -> None:
    """Save dictionary as TOML to path, preserving formatting and comments.

    Args:
        data: Dictionary or TOMLDocument to save as TOML
        path: Path where the TOML file should be saved

    """
    with open(path, "w", encoding="utf-8") as file:
        tomlkit.dump(data, file)  # type: ignore[arg-type]


def load_toml_from_path_and_merge_with_overrides(paths: Sequence[str | Path]) -> dict[str, Any]:
    """Load and merge toml files from paths if they exist, merged in sequence.

    Returns:
        dict[str, Any]: The merged dictionary
    """
    reject_bare_str_or_path(paths, param_name="paths")
    merged_dict: dict[str, Any] = {}
    for path in paths:
        if one_dict := load_toml_from_path_if_exists(path):
            deep_update(merged_dict, updates=one_dict)

    return merged_dict


def load_toml_from_base_and_overrides(paths: Sequence[str | Path]) -> dict[str, Any]:
    """The document at the first path, with each later path that exists deep-merged over it in order.

    The first path is the document and must exist — a missing one raises ``FileNotFoundError``
    exactly as ``load_toml_from_path`` would. The rest are overrides: each carries only the keys it
    sets, so an absent one is simply skipped, and a later one wins over an earlier one per leaf key.
    Tables merge; scalars and lists are replaced whole (``deep_update`` semantics).

    This is what distinguishes it from ``load_toml_from_path_and_merge_with_overrides``, where every
    path is optional and an empty sequence of files is an empty document: here the base's absence is
    the caller's error to report, because an override cannot stand in for the file it overrides.

    Args:
        paths: The base file first, then the override files in merge order.

    Returns:
        The merged dictionary.
    """
    reject_bare_str_or_path(paths, param_name="paths")
    base_path, *override_paths = paths
    merged_dict = load_toml_from_path(path=base_path)
    for override_path in override_paths:
        if override_dict := load_toml_from_path_if_exists(override_path):
            deep_update(merged_dict, updates=override_dict)
    return merged_dict


def describe_toml_base_and_overrides(*, paths: Sequence[str | Path]) -> str:
    """Name the files ``load_toml_from_base_and_overrides`` would merge, for an error message.

    The base, then only the overrides that exist: a user fixing a refusal edits one of the files
    that were actually read, and an absent override is not one of them.
    """
    base_path, *override_paths = paths
    description = f"'{base_path}'"
    present_overrides = [f"'{override_path}'" for override_path in override_paths if path_exists(override_path)]
    if present_overrides:
        description += f" with overrides {', '.join(present_overrides)}"
    return description
