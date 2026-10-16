from collections.abc import Iterator

import pytest

from pipelex.core.method_trees.method_file_store import LocalMethodFileStore
from pipelex.core.method_trees.tree_python import TREE_PYTHON_HOLD


@pytest.fixture
def released_hold() -> Iterator[None]:
    """Every hold a test takes on a tree's Python is released and its modules evicted, so the next test's tree can load."""
    yield
    TREE_PYTHON_HOLD.release_all()
    TREE_PYTHON_HOLD.unload_if_unheld()


@pytest.fixture
def store() -> LocalMethodFileStore:
    """A method file store of the test's own, holding nothing."""
    return LocalMethodFileStore()
