"""The method tree member a pipe is being built from, for the factories that resolve a file reference while building.

The library manager builds every pipe inside `building_pipe_of`, naming where its bundle lies:

- a `TreeBundle` for a bundle this host holds, read from its disk as a member of a method tree, or parsed from a content
  string and placed at the root of the tree of the files submitted with it: a factory resolves a file the step names,
  such as `PipeDocGen`'s `template_file`, in that tree, checks the file is there, and may read it to check it;
- a `TreeBundleRef` for a pipe built from a library crate, which names the tree by digest and carries no listing: a
  factory resolves the reference lexically and reads nothing, the host that assembled the crate having checked it;
- None for a bundle parsed from a content string with no file submitted beside it.

The tree is the only place a factory looks, so neither a `source` a caller labelled a bundle with nor one the bundle's
own text wrote can point a read at this host's disk.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeAlias

from pipelex.core.method_trees.tree_bundle import TreeBundle, TreeBundleRef

#: Where the bundle of a pipe being built lies: a tree this host holds, a tree a crate names, or none.
BuildingBundle: TypeAlias = TreeBundle | TreeBundleRef | None

_BUILDING_TREE_BUNDLE: ContextVar[BuildingBundle] = ContextVar("building_tree_bundle", default=None)


@contextmanager
def building_pipe_of(*, tree_bundle: BuildingBundle) -> Generator[None, None, None]:
    """Build the pipes inside this block as pipes of `tree_bundle`, as `BuildingBundle` describes it."""
    token = _BUILDING_TREE_BUNDLE.set(tree_bundle)
    try:
        yield
    finally:
        _BUILDING_TREE_BUNDLE.reset(token)


def get_building_tree_bundle() -> BuildingBundle:
    """Where the bundle of the pipe being built lies, as `BuildingBundle` describes it."""
    return _BUILDING_TREE_BUNDLE.get()
