"""Path helpers for accessing test data files."""

from importlib import resources
from pathlib import Path


def data_path(relative: str) -> Path:
    """Get the absolute path to a test data file.

    Args:
        relative: Relative path from tests/data directory

    Returns:
        Absolute path to the data file

    Example:
        >>> img = data_path("images/white_square.png")
        >>> doc = data_path("documents/solar_system.pdf")

    """
    data_dir = resources.files("tests.data")
    return Path(str(data_dir)) / relative
