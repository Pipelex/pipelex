"""Filesystem access to the corpus data files, which ship as package data inside the wheel."""

from importlib.resources import files
from pathlib import Path

CORPUS_PACKAGE = "pipelex.test_extras.mthds_corpus"
ENTRIES_DIR_NAME = "entries"


def corpus_root() -> Path:
    """The corpus tree's directory on disk.

    Resolved through ``importlib.resources`` so the corpus is reachable from an installed
    wheel and not only from a source checkout. Wheels install unzipped, so the traversable is
    a real filesystem path and no extraction step is needed — the same assumption the rest of
    pipelex's package-data access already makes.
    """
    return Path(str(files(CORPUS_PACKAGE)))


def entries_root() -> Path:
    """The directory holding one subdirectory per corpus entry."""
    return corpus_root() / ENTRIES_DIR_NAME
