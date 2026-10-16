"""A bundle as a member of its method tree, and a file of a method tree, as this host holds them and as a crate names them.

A bundle read from this host's disk is always read as a member of a method tree (`mthds/docs/spec/method-tree.md`),
listed by `mthds-python`'s lister: a library directory's tree, the tree of a method's folder, the tree of a `.mthds`
file named alone, or a dependency package's tree. A file the bundle's steps name, such as a `PipeDocGen` step's
`template_file`, is then resolved in that tree, by a lookup in its set of tree paths, and never by opening a path the
bundle wrote. Bundles parsed from content strings sit at the root of the tree of the files submitted with them, when
there are any, a tree this host assembled in memory (`LibraryManager`), and belong to no tree otherwise.

A library crate carries none of this: it names each bundle's tree by the tree's digest and the bundle by its tree path
(`TreeBundleRef`), and a step names a file of its tree the same way (`MethodFileRef`), so a crate travels without a
file's bytes or a path of the host that assembled it, and the process that uses a file reads it through the method file
store (`pipelex.core.method_trees.method_file_store`).
"""

from pathlib import Path

from mthds.method_tree.models import MethodTree
from pydantic import BaseModel, ConfigDict, Field


class TreeBundle(BaseModel):
    """A bundle of a method tree this host holds: the tree, and the bundle's tree path in it.

    `tree_path` is None for bundles parsed from content strings, which sit at the root of the tree of the files submitted
    with them without being a file of it: a reference they write resolves from the root.
    """

    model_config = ConfigDict(frozen=True)

    tree: MethodTree
    tree_path: str | None

    @property
    def location(self) -> Path:
        """Where the bundle's file lies on this host.

        Raises:
            ValueError: The bundle is not a file of a tree listed from a directory.
        """
        if self.tree_path is None:
            msg = "A bundle parsed from a content string has no file on this host."
            raise ValueError(msg)
        return self.tree.file_location(self.tree_path)

    def make_ref(self) -> "TreeBundleRef":
        """The bundle as a crate names it: its tree's digest and its tree path."""
        return TreeBundleRef(tree_digest=self.tree.digest, tree_path=self.tree_path)


class TreeBundleRef(BaseModel):
    """A bundle named by the digest of its tree and its tree path, as a library crate carries it.

    `tree_path` is None for bundles parsed from content strings, at the root of the tree of the files submitted with them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree_digest: str = Field(description="The digest of the bundle's tree, 'sha256:' and 64 lowercase hexadecimal digits")
    tree_path: str | None = Field(description="The bundle's tree path, or None for bundles at the root of the files submitted with them")


class MethodFileRef(BaseModel):
    """A file of a method tree: the digest of the tree that holds it, and its tree path there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree_digest: str = Field(description="The digest of the tree holding the file, 'sha256:' and 64 lowercase hexadecimal digits")
    tree_path: str = Field(description="The file's tree path, relative to the root of its tree")
