from __future__ import annotations

from typing import Any

import toml

from pipelex.tools.misc.file_utils import path_exists


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
        with open(path, encoding="utf-8") as file:
            content = file.read()

        # Parse TOML first
        return toml.loads(content)
    except toml.TomlDecodeError as exc:
        msg = f"TOML parsing error in file '{path}': {exc}"
        raise toml.TomlDecodeError(msg, exc.doc, exc.pos) from exc


def load_toml_from_path_if_exists(path: str) -> dict[str, Any] | None:
    """Load TOML from path if it exists."""
    if not path_exists(path):
        return None
    return load_toml_from_path(path)
