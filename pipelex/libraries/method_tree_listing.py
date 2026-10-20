"""One run's listing of the method trees it reads: each tree listed once, then handed down to every load of the run.

Listing a method tree walks its directory and hashes every file of it (`pipelex.libraries.method_trees`). A run needs the
tree it reads before it loads it, a CLI to resolve the folder or the bundle file it was handed and to record the tree's
digest, a server to check the requirements of the method it holds before the run starts, so the first lister makes a
`MethodTreeListing`, lists through it, and hands it down to the load. The load takes every tree from it, listing only the
trees nobody listed yet, and so one listing serves the whole run: the digest the run records is the digest of the tree it
loaded, and a large tree is hashed once.

A load given no listing makes its own, which serves that load alone. A listing belongs to one run: the files of a tree
may change between two runs, so a listing is never kept beyond the run that made it, and a command that writes the files
it lists, such as `fix`, makes a new one after each write.

The listing is handed down by argument, except across the bundle-validator seam, a plugin contract that names no
listing: a host validating through it puts its listing in scope around the call (`scoped_tree_listing`), and the
in-process validation takes it from there (`validate_bundles_in_process`), while a validator dispatching to another
process never reads it.

A listing also keeps the trees whose `requirements.txt` a check of the run found met (`pipelex.libraries.method_requirements`),
so each tree is judged once per run, and the package-offer factory of a sandbox-hosted deployment is asked once for it:
a later step of the load, or the load that follows a server's check of the method it holds, takes the verdict as given.
A refused tree is never kept, so a run that goes on after a refusal judges it again.

Every tree is listed under this machine's limits (`[interpreter.method_tree_limits]`), read once for the whole listing,
and a directory a host wrote a tree out as returns the tree as written, as every listing of it does
(`pipelex.libraries.written_trees`).
"""

import threading
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from mthds.method_tree.models import MethodTree, TreeLimits

from pipelex import log
from pipelex.core.method_trees.tree_bundle import TreeBundle
from pipelex.libraries.method_trees import (
    LibraryTree,
    library_trees_from,
    list_library_dir_tree,
    list_local_method_tree,
    listing_identity,
    local_tree_limits,
    lone_file_member,
)


def _listing_key(*, path: Path) -> Path:
    """The path a listing holds a tree under: resolved, so every spelling of one directory or file names one listing."""
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path.absolute()


class MethodTreeListing:
    """The method trees one run listed, each listed once, by the directory or the bundle file it was listed for.

    Its methods list as the functions of `pipelex.libraries.method_trees` do, and raise as they do, but list each
    directory or file once: a second ask, under any spelling of the same path, returns the tree the first listed. A
    listing that fails is not held, so asking again lists again and fails again.

    A run's loads use its listing one after another, possibly from different worker threads of the method-load pool, so
    every method holds the listing's lock while it lists.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._limits: TreeLimits | None = None
        # The tree each directory or bundle file handed over is rooted in, by its resolved path.
        self._rooted_trees: dict[Path, MethodTree] = {}
        # The trees each library directory holds, its own first, by the directory's resolved path.
        self._library_trees: dict[Path, list[MethodTree]] = {}
        # The trees whose requirements a check of the run found met, by their listing identity.
        self._trees_meeting_requirements: set[tuple[str, str, bool]] = set()

    @property
    def limits(self) -> TreeLimits:
        """This machine's limits, read from the configuration once for the whole listing.

        Raises:
            PipelexConfigError: Nothing booted and the configuration files do not validate.
        """
        with self._lock:
            if self._limits is None:
                self._limits = local_tree_limits()
            return self._limits

    def method_tree(self, *, handed_over: Path) -> MethodTree:
        """The method tree of a directory, or of a `.mthds` file named alone, listed once (`list_local_method_tree`).

        Raises:
            EmptyMethodTreeError: The membership rule keeps every file of the directory out of its tree.
            MethodTreeLoadError: The standard refused the tree otherwise, it passed a limit, or it could not be read.
            PipelexConfigError: Nothing booted and the configuration files, read for the limits, do not validate.
        """
        key = _listing_key(path=handed_over)
        with self._lock:
            tree = self._rooted_trees.get(key)
            if tree is None:
                tree = list_local_method_tree(handed_over=handed_over, limits=self.limits)
                self._rooted_trees[key] = tree
            return tree

    def lone_file_bundle(self, *, bundle_file: Path) -> TreeBundle:
        """A bundle file named alone as the member of its method tree, its tree listed once (`tree_bundle_of_lone_file`).

        Raises:
            MethodTreeLoadError: The tree could not be listed, or the membership rule keeps the file out of it.
            PipelexConfigError: Nothing booted and the configuration files, read for the limits, do not validate.
        """
        return lone_file_member(tree=self.method_tree(handed_over=bundle_file), bundle_file=bundle_file)

    def library_trees(self, *, library_dir: Path) -> list[MethodTree]:
        """The method trees a library directory holds, its own first, listed once (`list_library_trees`).

        The directory's own tree is the tree `method_tree` lists for it, so one listing serves a directory handed over as
        a method's folder and loaded as a library directory, whichever is asked first.

        Raises:
            MethodTreeLoadError: A tree could not be listed.
            PipelexConfigError: Nothing booted and the configuration files, read for the limits, do not validate.
        """
        key = _listing_key(path=library_dir)
        with self._lock:
            trees = self._library_trees.get(key)
            if trees is not None:
                return trees
            if not library_dir.exists():
                log.debug(f"A library directory that does not exist was skipped: {library_dir}")
                trees = []
            else:
                own_tree = self._rooted_trees.get(key)
                if own_tree is None:
                    own_tree = list_library_dir_tree(library_dir=library_dir, limits=self.limits)
                    if own_tree is not None:
                        self._rooted_trees[key] = own_tree
                trees = library_trees_from(library_dir=library_dir, own_tree=own_tree, limits=self.limits)
            self._library_trees[key] = trees
            return trees

    def meets_requirements(self, *, tree: MethodTree) -> bool:
        """Whether a check of the run already found the tree's requirements met, so no later check judges them again."""
        with self._lock:
            return listing_identity(tree=tree) in self._trees_meeting_requirements

    def record_requirements_met(self, *, tree: MethodTree) -> None:
        """Keep that a check found the tree's requirements met, which every later check of the run takes as given."""
        with self._lock:
            self._trees_meeting_requirements.add(listing_identity(tree=tree))

    def library_dir_trees(self, *, library_dirs: Iterable[Path]) -> list[LibraryTree]:
        """The method trees of the library directories, in the order given, each directory's own first (`list_library_dir_trees`).

        Raises:
            MethodTreeLoadError: A tree could not be listed.
            PipelexConfigError: Nothing booted and the configuration files, read for the limits, do not validate.
        """
        library_trees: list[LibraryTree] = []
        for library_dir in library_dirs:
            for tree in self.library_trees(library_dir=library_dir):
                library_trees.append(LibraryTree(library_dir=library_dir, tree=tree))
        return library_trees


# The listing a host put in scope around a call that takes none by argument, such as a bundle validator's.
_SCOPED_TREE_LISTING: ContextVar[MethodTreeListing | None] = ContextVar("scoped_tree_listing", default=None)


@contextmanager
def scoped_tree_listing(*, tree_listing: MethodTreeListing) -> Generator[None, None, None]:
    """Put a run's listing in scope for the calls made inside the block, and in the worker threads they load in.

    For a host whose listing must cross a seam that takes none by argument, such as the API server validating through a
    bundle validator once it has checked the method's requirements: the in-process validation inside the block loads the
    trees from it. The scope rides the context, so it reaches the method-load pool, which runs each load in a copy of it.
    """
    token = _SCOPED_TREE_LISTING.set(tree_listing)
    try:
        yield
    finally:
        _SCOPED_TREE_LISTING.reset(token)


def get_scoped_tree_listing() -> MethodTreeListing | None:
    """The listing a host put in scope (`scoped_tree_listing`), or None outside any."""
    return _SCOPED_TREE_LISTING.get()
