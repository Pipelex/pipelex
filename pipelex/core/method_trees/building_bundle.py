"""The method tree member a pipe is being built from, for the factories that resolve a file reference while building.

The library manager builds every pipe of a bundle it read from disk inside `building_pipe_of`, naming the bundle's
member of its method tree, and every pipe of a bundle parsed from a content string with none. A factory that resolves
a file the step names, such as `PipeDocGen`'s `template_file`, reads it here: the tree is the only place it looks, so
neither a `source` a caller labelled a bundle with nor one the bundle's own text wrote can point a read at this host's
disk.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from pipelex.core.method_trees.tree_bundle import TreeBundle

_BUILDING_TREE_BUNDLE: ContextVar[TreeBundle | None] = ContextVar("building_tree_bundle", default=None)


@contextmanager
def building_pipe_of(*, tree_bundle: TreeBundle | None) -> Generator[None, None, None]:
    """Build the pipes inside this block as pipes of `tree_bundle`, or of a bundle parsed from a string when None."""
    token = _BUILDING_TREE_BUNDLE.set(tree_bundle)
    try:
        yield
    finally:
        _BUILDING_TREE_BUNDLE.reset(token)


def get_building_tree_bundle() -> TreeBundle | None:
    """The member of its method tree the pipe being built was read from, or None for a bundle parsed from a string."""
    return _BUILDING_TREE_BUNDLE.get()
