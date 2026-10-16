"""A bundle as a member of its method tree: the tree it was listed in, and its tree path there.

A bundle read from this host's disk is always read as a member of a method tree (`mthds/docs/spec/method-tree.md`),
listed by `mthds-python`'s lister: a library directory's tree, the tree of a method's folder, the tree of a `.mthds`
file named alone, or a dependency package's tree. A file the bundle's steps name, such as a `PipeDocGen` step's
`template_file`, is then resolved in that tree, by a lookup in its set of tree paths, and never by opening a path the
bundle wrote. A bundle parsed from a content string belongs to no tree here.
"""

from pathlib import Path

from mthds.method_tree.models import MethodTree
from pydantic import BaseModel, ConfigDict


def tree_key_of(*, tree: MethodTree) -> str:
    """The key a tree is held under where several travel together, such as in a library crate.

    Two listings of one directory with the same files share a key, and a one-file tree never shares one with the
    directory tree of its folder, since only the latter lets a reference reach another file.
    """
    kind = "one-file" if tree.is_one_file else "directory"
    return f"{kind}:{tree.directory}:{tree.digest}"


class TreeBundle(BaseModel):
    """A bundle file of a method tree: the tree, listed from this host's disk, and the bundle's tree path in it."""

    model_config = ConfigDict(frozen=True)

    tree: MethodTree
    tree_path: str

    @property
    def tree_key(self) -> str:
        return tree_key_of(tree=self.tree)

    @property
    def location(self) -> Path:
        """Where the bundle's file lies on this host."""
        return self.tree.file_location(self.tree_path)


class TreeBundleRef(BaseModel):
    """A bundle file named by the key of its tree and its tree path, as a library crate carries it beside its trees."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree_key: str
    tree_path: str
