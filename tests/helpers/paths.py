"""Path helpers for accessing test data files."""

from pathlib import Path

TESTS_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


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
    return TESTS_DATA_DIR / relative
