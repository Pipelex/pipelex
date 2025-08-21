from __future__ import annotations

import os
from typing import Final

REQUIRED_PIPELEX_SUBDIRS: Final[list[str]] = [
    "pipelines",
    "llm_deck",
    "llm_integrations",
    "plugins",
    "templates",
]


def is_pipelex_libraries_folder(folder_path: str) -> bool:
    """Check if the given folder path contains a valid pipelex libraries structure."""
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return False

    for subdir in REQUIRED_PIPELEX_SUBDIRS:
        subdir_path = os.path.join(folder_path, subdir)
        if not os.path.exists(subdir_path) or not os.path.isdir(subdir_path):
            return False

    return True
