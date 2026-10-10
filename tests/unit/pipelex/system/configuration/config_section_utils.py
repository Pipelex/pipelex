"""Sections of the package's own `pipelex.toml`, the valid documents the member-type tests each spoil one member of."""

import tomllib
from typing import Any

from pipelex.system.configuration.config_loader import CONFIG_NAME, ConfigLoader


def base_config_section(*section_path: str) -> dict[str, Any]:
    """A section of the package's own `pipelex.toml`, the valid document each test spoils one member of."""
    section: dict[str, Any] = tomllib.loads((ConfigLoader().pipelex_root_dir / CONFIG_NAME).read_text(encoding="utf-8"))
    for key in section_path:
        section = section[key]
    return section
