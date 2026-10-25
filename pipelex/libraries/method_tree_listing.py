"""One run's listing of the method trees it reads: each tree listed once, then handed down to every load of the run.

Listing a method tree walks its directory and hashes every file of it (`pipelex.libraries.method_trees`). A run needs the
tree it reads before it loads it, a CLI to resolve the folder or the bundle file it was handed and to record the tree's
digest, a server to check the requirements of the method it holds before the run starts, so the first lister makes a
`MethodTreeListing`, lists through it, and hands it down to the load. The load takes every tree from it, listing only the
trees nobody listed yet, and so one listing serves the whole run: the digest the run records is the digest of the tree it
loaded.

A listing holds each tree by its root, so a folder handed over as a method, the same folder loaded as a library
directory, and a bundle file named alone inside it are one listing of one tree, whichever is asked first. It reads the
path handed over exactly as the standard's lister does before taking anything from what it holds: a directory, or a
symbolic link naming one, is followed to the directory it names, as the lister follows it, while a `.mthds` file named
alone is never followed, so a symbolic link named alone is refused as the lister refuses it, even when the run already
listed the file it points to.

The files of a tree may change after its listing. Every read of them is checked against the hashes the listing recorded
(`read_tree_file_as_listed`), and a load (`loading`) reads again every file of each tree it takes that the run listed
before any load, once, as it takes it, so a tree edited between its listing and its load is refused before anything of
it is parsed or run, with `MethodTreeChangedError`, in the context of the load that takes it; a tree a load lists itself
is as fresh as that check would be. A listing belongs to one run: it is never kept beyond the run that made it, and a
command that writes the files it lists, such as `fix`, makes a new one after each write.

The listing is handed down by argument, except across the bundle-validator seam, a plugin contract that names no
listing: a host validating through it puts its listing in scope around the call (`scoped_tree_listing`), and the
in-process validation takes it from there (`validate_bundles_in_process`), while a validator dispatching to another
process never reads it.

A listing also keeps the verdicts on the trees whose `requirements.txt` a check of the run found met
(`pipelex.libraries.method_requirements`), each with what it was judged against, the PipeFunc execution mode and the
plugin factory stating its packages, so each tree is judged once per run against one environment, and the package-offer
factory of a sandbox-hosted deployment is asked once for it, even by loads judging it at the same time. A refused tree
is never kept, so a run that goes on after a refusal judges it again.

Its loads may run at the same time in different worker threads of the method-load pool, so each tree is listed, checked
and judged under a lock of its own: a second ask waits for the first and takes its tree, while trees of different paths
are listed side by side.

Every tree is listed under this machine's limits (`[interpreter.method_tree_limits]`), read once for the whole listing,
and a directory a host wrote a tree out as returns the tree as written, as every listing of it does
(`pipelex.libraries.written_trees`).
"""

import threading
from collections.abc import Callable, Generator, Hashable, Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from mthds.method_tree.models import MethodTree, TreeLimits

from pipelex.core.method_trees.tree_bundle import TreeBundle
from pipelex.libraries.method_trees import (
    HandedOverLocation,
    LibraryTree,
    ensure_tree_files_as_listed,
    list_library_dir_tree,
    list_library_dir_trees,
    list_library_trees,
    list_local_method_tree,
    list_package_method_tree,
    listing_identity,
    local_tree_limits,
    locate_handed_over,
    lone_file_member,
    lone_file_tree_path,
)
from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES

TreeIdentity = tuple[str, str, bool]


def _resolved_or_absolute(*, path: Path) -> Path:
    """A path as a key: resolved, as the lister resolves a directory, or absolute when it cannot be resolved."""
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return path.absolute()


class MethodTreeListing:
    """The method trees one run listed, each listed once, with the checks the run made of them.

    Its methods list as the functions of `pipelex.libraries.method_trees` do, and raise as they do, but list each tree
    once: a second ask, under any spelling the standard's lister reads as the same tree, returns the tree the first
    listed. A listing that fails is not held, so asking again lists again and fails again.
    """

    def __init__(self) -> None:
        # Guards the maps below, and is never held while a tree is listed, checked or judged.
        self._lock = threading.Lock()
        # One lock per tree, path or verdict being worked on, so concurrent asks of one wait while the others proceed.
        self._key_locks: dict[Hashable, threading.RLock] = {}
        self._limits: TreeLimits | None = None
        # The tree of each root, as a directory handed over or a library directory lists it, with no entry.
        self._trees_by_root: dict[Path, MethodTree] = {}
        # The tree of each `.mthds` file named alone, by the file's location, its own name never followed.
        self._lone_file_trees: dict[Path, MethodTree] = {}
        # The trees each library directory holds, its own first, by the directory's resolved path.
        self._library_trees: dict[Path, list[MethodTree]] = {}
        # Each dependency package's tree, rooted at the package's own directory, by that directory's resolved path.
        self._package_trees: dict[Path, MethodTree] = {}
        # The trees a load reading this listing took fresh from the disk, by listing them or by reading them again.
        self._trees_read_by_a_load: set[TreeIdentity] = set()
        # What each tree was found to meet its requirements against: the environment sources of its verdicts.
        self._requirements_met: dict[TreeIdentity, list[object]] = {}

    def _key_lock(self, *, key: Hashable) -> threading.RLock:
        with self._lock:
            key_lock = self._key_locks.get(key)
            if key_lock is None:
                key_lock = threading.RLock()
                self._key_locks[key] = key_lock
            return key_lock

    @property
    def limits(self) -> TreeLimits:
        """This machine's limits, read from the configuration once for the whole listing.

        Raises:
            PipelexConfigError: Nothing booted and the configuration files do not validate.
        """
        with self._key_lock(key="limits"):
            if self._limits is None:
                self._limits = local_tree_limits()
            return self._limits

    def _handed_out(self, *, tree: MethodTree, listed_now: bool) -> MethodTree:
        """Hand a tree out: to a load, a tree listed before any load is read again first, once (`loading`).

        `listed_now` says the tree was just read from the disk by the lister, so a load taking it needs no second read. A
        tree a host wrote out is read as written, never again.

        Raises:
            MethodTreeChangedError: A load takes a tree listed before it, and a file of it is not the file its listing hashed.
        """
        if tree.directory is None or not self._is_loading():
            return tree
        if listed_now or WRITTEN_METHOD_TREES.holds_tree(tree=tree):
            # A tree a host wrote out is read as written, from the files the host wrote, and never read again.
            with self._lock:
                self._trees_read_by_a_load.add(listing_identity(tree=tree))
        else:
            self._check_tree(tree=tree)
        return tree

    def _is_loading(self) -> bool:
        return any(listing is self for listing in _LOADING_LISTINGS.get())

    def _held_root_tree(self, *, root: Path) -> MethodTree | None:
        with self._lock:
            return self._trees_by_root.get(root)

    def _hold_root_tree(self, *, tree: MethodTree) -> None:
        """Hold a directory tree under its root, the entry a lone file's listing names dropped, for every later ask of the root."""
        if tree.directory is None or tree.is_one_file:
            return
        root_tree = tree if tree.entry is None else tree.model_copy(update={"entry": None})
        with self._lock:
            self._trees_by_root.setdefault(tree.directory, root_tree)

    def method_tree(self, *, handed_over: Path) -> MethodTree:
        """The method tree of a directory, or of a `.mthds` file named alone, listed once (`list_local_method_tree`).

        Raises:
            EmptyMethodTreeError: The membership rule keeps every file of the directory out of its tree.
            MethodTreeLoadError: The standard refused the tree otherwise, it passed a limit, or it could not be read.
            PipelexConfigError: Nothing booted and the configuration files, read for the limits, do not validate.
        """
        location = locate_handed_over(handed_over=handed_over)
        if location is not None and location.lone_file is not None:
            return self._lone_file_tree(location=location, lone_file=location.lone_file, handed_over=handed_over)
        if location is None or location.root is None:
            # The lister refuses the path before listing anything: it gives the refusal.
            return self._handed_out(tree=list_local_method_tree(handed_over=handed_over, limits=self.limits), listed_now=True)
        with self._key_lock(key=("root", location.root)):
            tree = self._held_root_tree(root=location.root)
            if tree is not None:
                return self._handed_out(tree=tree, listed_now=False)
            tree = list_local_method_tree(handed_over=handed_over, limits=self.limits)
            self._hold_root_tree(tree=tree)
            return self._handed_out(tree=tree, listed_now=True)

    def _library_dir_own_tree(self, *, library_dir: Path, limits: TreeLimits) -> MethodTree | None:
        """The tree a library directory is rooted in, or None when it is empty, taken from the root it shares (`list_library_dir_tree`)."""
        location = locate_handed_over(handed_over=library_dir)
        if location is None or location.directory is None or location.root is None:
            # Not a directory as the lister reads one: it gives what it gives such a path.
            listed = list_library_dir_tree(library_dir=library_dir, limits=limits)
            return self._handed_out(tree=listed, listed_now=True) if listed is not None else None
        with self._key_lock(key=("root", location.root)):
            tree = self._held_root_tree(root=location.root)
            if tree is not None:
                return self._handed_out(tree=tree, listed_now=False)
            tree = list_library_dir_tree(library_dir=library_dir, limits=limits)
            if tree is None:
                return None
            self._hold_root_tree(tree=tree)
            return self._handed_out(tree=tree, listed_now=True)

    def _lone_file_tree(self, *, location: HandedOverLocation, lone_file: Path, handed_over: Path) -> MethodTree:
        with self._key_lock(key=("lone_file", lone_file)):
            with self._lock:
                tree = self._lone_file_trees.get(lone_file)
            listed_now = False
            if tree is None:
                tree = self._lone_file_tree_from_root(location=location, lone_file=lone_file)
            if tree is None:
                tree = list_local_method_tree(handed_over=handed_over, limits=self.limits)
                listed_now = True
                self._hold_root_tree(tree=tree)
            with self._lock:
                self._lone_file_trees.setdefault(lone_file, tree)
            return self._handed_out(tree=tree, listed_now=listed_now)

    def _lone_file_tree_from_root(self, *, location: HandedOverLocation, lone_file: Path) -> MethodTree | None:
        """A lone file's tree from its root's tree listed already, when that tree holds the file, else None for the lister to list it.

        The lister lists a lone file under a `METHODS.toml` as the walk of the root that lists the root itself, naming
        the file as its entry: the walk the root's listing made. A file the walk did not keep, such as one a `.gitignore`
        keeps out, is left to the lister, whose refusal names why.
        """
        if location.root is None:
            return None
        with self._key_lock(key=("root", location.root)):
            root_tree = self._held_root_tree(root=location.root)
        if root_tree is None:
            return None
        entry = lone_file_tree_path(root=location.root, lone_file=lone_file)
        if entry is None or entry not in root_tree.members:
            return None
        return root_tree.model_copy(update={"entry": entry})

    def lone_file_bundle(self, *, bundle_file: Path) -> TreeBundle:
        """A bundle file named alone as the member of its method tree, its tree listed once (`method_tree`).

        Raises:
            MethodTreeLoadError: The tree could not be listed, or the membership rule keeps the file out of it.
            PipelexConfigError: Nothing booted and the configuration files, read for the limits, do not validate.
        """
        return lone_file_member(tree=self.method_tree(handed_over=bundle_file), bundle_file=bundle_file)

    def library_trees(self, *, library_dir: Path) -> list[MethodTree]:
        """The method trees a library directory holds, its own first, listed once (`list_library_trees`).

        The directory's own tree is the tree of its root, which `method_tree` lists too, so one listing serves a directory
        handed over as a method's folder and loaded as a library directory, whichever is asked first.

        Raises:
            MethodTreeLoadError: A tree could not be listed.
            PipelexConfigError: Nothing booted and the configuration files, read for the limits, do not validate.
        """
        key = _resolved_or_absolute(path=library_dir)
        with self._key_lock(key=("library", key)):
            with self._lock:
                trees = self._library_trees.get(key)
            if trees is not None:
                for tree in trees:
                    self._handed_out(tree=tree, listed_now=False)
                return trees
            # The directory's own tree is handed out as it is taken (`_library_dir_own_tree`), read again when it was held
            # already, and the trees nested in it are listed now.
            trees = list_library_trees(library_dir=library_dir, limits=self.limits, own_tree_of=self._library_dir_own_tree)
            with self._lock:
                self._library_trees[key] = trees
            for tree in trees:
                self._handed_out(tree=tree, listed_now=True)
            return trees

    def _library_trees_of(self, *, library_dir: Path, limits: TreeLimits) -> list[MethodTree]:  # ruff: ignore[unused-method-argument]
        # The listing's own limits, read once, are the ones `list_library_dir_trees` was handed.
        return self.library_trees(library_dir=library_dir)

    def library_dir_trees(self, *, library_dirs: Iterable[Path]) -> list[LibraryTree]:
        """The method trees of the library directories, in the order given, each directory's own first (`list_library_dir_trees`).

        Raises:
            MethodTreeLoadError: A tree could not be listed.
            PipelexConfigError: Nothing booted and the configuration files, read for the limits, do not validate.
        """
        return list_library_dir_trees(library_dirs=library_dirs, limits=self.limits, trees_of=self._library_trees_of)

    def package_tree(self, *, root: Path, package_address: str) -> MethodTree:
        """A dependency package's tree, rooted at the package's own directory, listed once (`list_package_method_tree`).

        Raises:
            MethodTreeLoadError: The standard refused the tree, it passed a limit, or it could not be read, named by the
                package's address.
            PipelexConfigError: Nothing booted and the configuration files, read for the limits, do not validate.
        """
        key = _resolved_or_absolute(path=root)
        with self._key_lock(key=("package", key)):
            with self._lock:
                tree = self._package_trees.get(key)
            if tree is not None:
                return self._handed_out(tree=tree, listed_now=False)
            tree = list_package_method_tree(root=root, package_address=package_address, limits=self.limits)
            with self._lock:
                self._package_trees[key] = tree
            return self._handed_out(tree=tree, listed_now=True)

    def judge_requirements_once(self, *, tree: MethodTree, judged_against: object, judge: Callable[[], None]) -> None:
        """Judge a tree's requirements once per run against one environment: `judge` runs unless a check of the run found them met.

        `judged_against` names what the verdict depends on beyond the tree, compared with `==`: the PipeFunc execution
        mode and the plugin factory stating its packages, so a check and a load judging against different ones never
        share a verdict. Two loads judging the tree at once judge it once, the second taking the first's verdict, or
        judging it again when the first refused it, since a refusal is never kept.

        Raises:
            Whatever `judge` raises: the tree's refusal, which is not kept.
        """
        identity = listing_identity(tree=tree)
        with self._key_lock(key=("requirements", identity)):
            with self._lock:
                if any(environment == judged_against for environment in self._requirements_met.get(identity, ())):
                    return
            judge()
            with self._lock:
                self._requirements_met.setdefault(identity, []).append(judged_against)

    def _check_tree(self, *, tree: MethodTree) -> None:
        identity = listing_identity(tree=tree)
        with self._key_lock(key=("check", identity)):
            with self._lock:
                if identity in self._trees_read_by_a_load:
                    return
            ensure_tree_files_as_listed(tree=tree)
            with self._lock:
                self._trees_read_by_a_load.add(identity)

    def ensure_unchanged(self, *, tree: MethodTree) -> None:
        """Read a tree a load takes from elsewhere than this listing's methods again, once, as a tree they hand to a load is.

        For a bundle a caller placed in its tree before the load, such as a bundle file a command or a validation read
        alone: the load takes the tree from the bundle, so the check `loading` makes of a tree it takes from the listing
        is made here. A tree a host wrote out, or one read from a map of file entries, is never read again.

        Raises:
            MethodTreeChangedError: A file of the tree is not the file its listing hashed.
        """
        if tree.directory is None or WRITTEN_METHOD_TREES.holds_tree(tree=tree):
            return
        self._check_tree(tree=tree)

    @contextmanager
    def loading(self) -> Generator[None, None, None]:
        """Mark a load reading this listing: each tree it takes that the run listed before any load is read again first.

        A tree the run listed before a load, such as the folder a command resolved or the method a server checked, may
        have changed since: as the load takes it, each of its files is read again and refused unless it is the file the
        listing hashed, so a changed tree is refused before anything of it is parsed, imported or run, and the refusal
        is raised where the load takes the tree, in the context that reports the load's own faults. A tree a load lists
        itself is as fresh as that check, a tree is read again once per run, and a load nested in another reading the
        same listing is that load.
        """
        loading_listings = _LOADING_LISTINGS.get()
        if any(listing is self for listing in loading_listings):
            yield
            return
        token = _LOADING_LISTINGS.set((*loading_listings, self))
        try:
            yield
        finally:
            _LOADING_LISTINGS.reset(token)


# The listings a load in this context reads, so a tree it lists counts as read and a nested load checks nothing again.
_LOADING_LISTINGS: ContextVar[tuple[MethodTreeListing, ...]] = ContextVar("loading_tree_listings", default=())

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
