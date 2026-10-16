"""Importing a method tree's Python in this process: one tree at a time, guarded, and evicted before the next.

A `PipeFunc` names its function by import path from the root of its method tree, so a run that calls one imports the
tree's modules under their real names, with the tree's root first on `sys.path` (`wip/extra-files/design.md`, D3).
Only the in-process `direct` mode does this; a sandbox-hosted deployment never imports a tree's Python in its own
process. Four rules keep that safe:

- **One tree's Python per process at a time** (D19). A run holds the tree whose Python it imports from its first
  `PipeFunc` step until its library is torn down, and every run of the same tree shares the hold. Loading another
  tree's Python while one is held is refused, naming both trees, since two trees' modules share one import namespace.
- **Eviction before the next tree** (D8). Once no run holds a tree, the next tree to load first evicts every module
  imported from the earlier tree's root from `sys.modules` and drops that root from `sys.path`, so a process running
  several methods one after the other never runs one method's module for another's step.
- **No shadowing** (D9). A top-level module of the tree named like a standard-library module, or like a module
  importable outside the tree, is refused, naming both, since the tree's would replace it for the whole process. The
  `structures` module keeps its documented exception: the runtime generates it from a method's concepts, and a
  method's own copy of it is the intended one.
- **The local import guard** (D22). While a tree is held, a finder first on `sys.meta_path` serves the modules under
  its root: a file the tree's membership rule keeps out, such as a `.gitignore`d file or a virtual environment, is
  refused with the rule that excluded it. A member is loaded without writing bytecode, so a `__pycache__` never
  appears in the tree, which matters for a package cache digested as written. Python's own `open()` reads stay
  unchecked locally: the guard covers imports only.
"""

import importlib
import importlib.abc
import importlib.machinery
import sys
import threading
from collections.abc import Collection, Iterable, Mapping, Sequence
from pathlib import Path
from types import ModuleType
from typing import NamedTuple

from mthds.method_tree.models import MethodTree
from mthds.method_tree.tree_path import nfc
from typing_extensions import Buffer, override

from pipelex.core.method_trees.exceptions import TreeModuleExcludedError, TreeModuleShadowingError, TreePythonError, TreePythonHeldError

#: The module the runtime generates from a method's concepts, which a tree may ship itself (the shadowing exception).
GENERATED_STRUCTURES_MODULE = "structures"

_PYTHON_SUFFIX = ".py"
_PACKAGE_INIT = "__init__"


class TreePythonIdentity(NamedTuple):
    """A tree whose Python a process imports: its root on this host and its digest, which changes with any file."""

    root: Path
    digest: str

    def describe(self) -> str:
        """The tree, named for a message: its root and the start of its digest."""
        return f"the method tree at {self.root} ({self.digest[:19]})"


def tree_python_identity(*, tree: MethodTree) -> TreePythonIdentity:
    """The identity of a tree listed from a directory of this host, whose root is its import root.

    Raises:
        TreePythonError: The tree was read from a map of file entries, or is the one-file tree of a lone bundle, so it
            has no directory of Python to import from.
    """
    if tree.directory is None:
        msg = "The method tree was read from a map of file entries and has no directory on this host, so its Python cannot be imported here."
        raise TreePythonError(msg)
    if tree.is_one_file:
        msg = (
            f"The bundle at {tree.directory} was read alone, as a one-file tree, which holds no Python: hand over the method's folder, "
            "whose tree holds the bundle and its Python."
        )
        raise TreePythonError(msg)
    return TreePythonIdentity(root=tree.directory.resolve(), digest=tree.digest)


def top_level_module_names(*, tree_paths: Iterable[str]) -> dict[str, str]:
    """The top-level modules a tree's Python defines, each with the first tree path that defines it.

    A Python file at the root defines the module of its stem; a directory holding a Python file at any depth defines
    the module, or namespace package, of its name. A name that is not an identifier cannot be imported and defines
    nothing.
    """
    modules: dict[str, str] = {}
    for tree_path in sorted(tree_paths):
        if not tree_path.endswith(_PYTHON_SUFFIX):
            continue
        first_segment, separator, _ = tree_path.partition("/")
        module_name = first_segment if separator else first_segment.removesuffix(_PYTHON_SUFFIX)
        if module_name == _PACKAGE_INIT or not module_name.isidentifier():
            continue
        modules.setdefault(module_name, tree_path)
    return modules


def check_tree_module_names(*, top_level_modules: Mapping[str, str], tree_label: str, root: Path | None) -> None:
    """Refuse a tree whose top-level module shares its name with a standard-library module or one importable outside the tree.

    Args:
        top_level_modules: The tree's top-level modules, each with the tree path that defines it.
        tree_label: How the message names the tree.
        root: The tree's root on this host, whose own modules are not outside it; None for files with no directory here.

    Raises:
        TreeModuleShadowingError: A module would shadow another, named with the tree file and what it shadows.
    """
    earlier_roots = TREE_PYTHON_HOLD.loaded_roots()
    for module_name, tree_path in sorted(top_level_modules.items()):
        if module_name == GENERATED_STRUCTURES_MODULE:
            continue
        shadowed = _module_outside_tree(module_name=module_name, root=root, earlier_roots=earlier_roots)
        if shadowed is None:
            continue
        msg = (
            f"The file {tree_path} of {tree_label} defines the top-level module '{module_name}', which shares its name with {shadowed}. "
            "With the tree's root first on the import path, it would replace that module for the whole process: rename it, "
            "for example by moving it into a package of the method's own."
        )
        raise TreeModuleShadowingError(msg)


def _module_outside_tree(*, module_name: str, root: Path | None, earlier_roots: Collection[Path]) -> str | None:
    """What a top-level name already names outside the tree, described for a message, or None when it names nothing."""
    if module_name in sys.stdlib_module_names or module_name in sys.builtin_module_names:
        return f"the standard-library module '{module_name}'"
    # The module is named without its location, which is a path on this host that a caller's verdict must not show.
    loaded = sys.modules.get(module_name)
    if loaded is not None:
        location = _module_location(module=loaded)
        if location is not None and _is_tree_location(location=location, root=root, earlier_roots=earlier_roots):
            return None
        return f"the module '{module_name}', already imported in this process"
    for spec in _specs_outside_root(module_name=module_name, root=root):
        if spec.origin is None or not spec.has_location:
            # A namespace portion never shadows a regular module, and a regular module of the tree takes precedence over it.
            continue
        if _is_tree_location(location=Path(spec.origin), root=root, earlier_roots=earlier_roots):
            continue
        return f"the module '{module_name}', importable in this process outside the tree"
    return None


def _specs_outside_root(*, module_name: str, root: Path | None) -> list[importlib.machinery.ModuleSpec]:
    """The specs this process's finders return for a top-level name when the tree's root is not searched."""
    specs: list[importlib.machinery.ModuleSpec] = []
    for finder in list(sys.meta_path):
        if isinstance(finder, TreeModuleGuard):
            continue
        spec: importlib.machinery.ModuleSpec | None
        if finder is importlib.machinery.PathFinder:
            entries = [entry for entry in sys.path if root is None or not _is_same_directory(entry=entry, directory=root)]
            spec = importlib.machinery.PathFinder.find_spec(module_name, entries)
        else:
            find_spec = getattr(finder, "find_spec", None)
            if find_spec is None:
                continue
            try:
                spec = find_spec(module_name, None)
            except (ImportError, ValueError):
                continue
        if spec is not None:
            specs.append(spec)
    return specs


def _module_location(*, module: ModuleType) -> Path | None:
    """Where a loaded module's file, or its first package directory, lies on disk, else None."""
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str):
        return Path(module_file)
    module_path = getattr(module, "__path__", None)
    if module_path is not None:
        for entry in module_path:
            return Path(entry)
    return None


def _is_tree_location(*, location: Path, root: Path | None, earlier_roots: Collection[Path]) -> bool:
    """Whether a location lies under the tree's root, or under an earlier tree's root that a load evicts first."""
    candidates = [*earlier_roots, *([root] if root is not None else [])]
    return any(_is_under(path=location, directory=directory) for directory in candidates)


def _is_under(*, path: Path, directory: Path) -> bool:
    try:
        return path.resolve().is_relative_to(directory.resolve())
    except OSError:
        return False


def _is_same_directory(*, entry: str, directory: Path) -> bool:
    try:
        return Path(entry or ".").resolve() == directory.resolve()
    except OSError:
        return False


class _TreeSourceLoader(importlib.machinery.SourceFileLoader):
    """Loads a module of a held tree from its source, and never writes bytecode beside it."""

    def __init__(self, fullname: str, path: str, *, tree_root: Path):
        super().__init__(fullname, path)
        self.tree_root = tree_root

    @override
    def set_data(self, path: str, data: Buffer, *, _mode: int = 0o666) -> None:  # kw-only: ignore
        # The only data a source loader writes is the bytecode cache: a tree on disk, a package cache digested as
        # written included, is never written into.
        return


class TreeModuleGuard(importlib.abc.MetaPathFinder):
    """The finder first on `sys.meta_path` while a tree is held: it serves the tree's modules, and refuses the files the tree excludes.

    A top-level import is looked up at the tree's root first, as the root is first on `sys.path`; a submodule import
    is looked up in its package's directories that lie under the root. A module found there whose file is a member of
    the tree is loaded without writing bytecode; one whose file the tree's membership rule keeps out is refused,
    naming the file and the rule. A namespace package is left to Python's own machinery, which merges its portions;
    the modules under it are guarded as they are imported.
    """

    def __init__(self, *, tree: MethodTree, root: Path):
        self._tree = tree
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    @override
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        search_entries: list[str]
        if path is None:
            search_entries = [str(self._root)]
        else:
            search_entries = [entry for entry in path if _is_under(path=Path(entry), directory=self._root)]
            if not search_entries:
                return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, search_entries)
        if spec is None or spec.origin is None or not spec.has_location:
            return None
        location = Path(spec.origin).resolve()
        if not location.is_relative_to(self._root):
            return None
        tree_path = nfc(location.relative_to(self._root).as_posix())
        if tree_path not in self._tree.members:
            msg = (
                f"The import of '{fullname}' reached the file {location}, under the root of the method tree at {self._root}, "
                f"but the tree keeps that file out: {self._exclusion_reason(tree_path=tree_path)}. "
                "A method's Python imports only the files of its own tree."
            )
            raise TreeModuleExcludedError(msg, module_name=fullname, file_path=location)
        if isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            spec.loader = _TreeSourceLoader(fullname, str(location), tree_root=self._root)
        return spec

    def _exclusion_reason(self, *, tree_path: str) -> str:
        """The rule that keeps a tree path out of the tree, in words."""
        exclusion = self._tree.excluded_files.get(tree_path)
        if exclusion is None:
            matching_directories = [directory for directory in self._tree.excluded_directories if tree_path.startswith(f"{directory}/")]
            if matching_directories:
                exclusion = self._tree.excluded_directories[max(matching_directories, key=len)]
        if exclusion is None:
            return "it is not a member of the tree as it was listed, which happens to a file created since"
        return f"the membership rule excludes it, for {exclusion.rule.description}"


class TreePythonHold:
    """Which tree's Python this process imports, and which runs hold it; one per process (`TREE_PYTHON_HOLD`)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loaded: TreePythonIdentity | None = None
        self._holders: set[str] = set()
        self._guard: TreeModuleGuard | None = None

    def loaded_roots(self) -> list[Path]:
        """The root of the tree whose Python is loaded, held or not, which the next other tree's load evicts."""
        loaded = self._loaded
        return [loaded.root] if loaded is not None else []

    def acquire(self, *, tree: MethodTree, holder: str) -> TreePythonIdentity:
        """Hold the tree's Python for `holder`, loading it first when another tree's is loaded and no run holds it.

        Loading checks the tree's top-level module names, evicts the earlier tree's modules and root, puts this tree's
        root first on `sys.path` and installs the import guard first on `sys.meta_path`.

        Args:
            tree: The tree, listed from a directory of this host.
            holder: Who holds it: the library of the run, released when that library is torn down.

        Returns:
            The identity of the held tree.

        Raises:
            TreePythonHeldError: Another tree's Python is held by a run in flight.
            TreeModuleShadowingError: A top-level module of the tree would shadow another module.
            TreePythonError: The tree has no directory of Python on this host.
        """
        identity = tree_python_identity(tree=tree)
        with self._lock:
            if self._loaded == identity:
                if not self._holders:
                    if str(identity.root) not in sys.path:
                        sys.path.insert(0, str(identity.root))
                    self._install_guard(tree=tree, root=identity.root)
                self._holders.add(holder)
                return identity
            if self._loaded is not None and self._holders:
                msg = (
                    f"The Python of {identity.describe()} cannot load while a run holds the Python of {self._loaded.describe()}: "
                    "a process imports one method tree's Python at a time, since the modules of two trees share one import "
                    "namespace. Run the two methods one after the other, or in separate processes."
                )
                raise TreePythonHeldError(msg)
            check_tree_module_names(
                top_level_modules=top_level_module_names(tree_paths=tree.members),
                tree_label=identity.describe(),
                root=identity.root,
            )
            if self._loaded is not None:
                self._evict(root=self._loaded.root)
            self._loaded = identity
            sys.path.insert(0, str(identity.root))
            self._install_guard(tree=tree, root=identity.root)
            importlib.invalidate_caches()
            self._holders.add(holder)
            return identity

    def release(self, *, holder: str) -> None:
        """Release the hold `holder` took, if any; the tree's modules stay loaded until another tree's load evicts them."""
        with self._lock:
            if holder not in self._holders:
                return
            self._holders.discard(holder)
            if not self._holders:
                self._remove_guard()

    def release_all(self) -> None:
        """Release every hold, as the process tears its libraries down."""
        with self._lock:
            self._holders.clear()
            self._remove_guard()

    def unload_if_unheld(self) -> None:
        """Evict the loaded tree's modules and root now, if no run holds it, as before its directory is removed."""
        with self._lock:
            loaded = self._loaded
            if loaded is None or self._holders:
                return
            self._evict(root=loaded.root)
            self._loaded = None

    def is_held(self, *, identity: TreePythonIdentity) -> bool:
        """Whether a run holds this tree's Python."""
        return self._loaded == identity and bool(self._holders)

    def _install_guard(self, *, tree: MethodTree, root: Path) -> None:
        self._remove_guard()
        guard = TreeModuleGuard(tree=tree, root=root)
        sys.meta_path.insert(0, guard)
        self._guard = guard

    def _remove_guard(self) -> None:
        guard = self._guard
        if guard is None:
            return
        sys.meta_path[:] = [finder for finder in sys.meta_path if finder is not guard]
        self._guard = None

    @staticmethod
    def _evict(*, root: Path) -> None:
        """Remove every module imported from `root` under the hold from `sys.modules`, and `root` from `sys.path`."""
        for module_name, module in list(sys.modules.items()):
            spec = getattr(module, "__spec__", None)
            if spec is None:
                continue
            loader = spec.loader
            if isinstance(loader, _TreeSourceLoader):
                if loader.tree_root == root:
                    del sys.modules[module_name]
                continue
            if spec.origin is None and spec.submodule_search_locations is not None:
                portions = [Path(portion) for portion in spec.submodule_search_locations]
                if portions and all(_is_under(path=portion, directory=root) for portion in portions):
                    del sys.modules[module_name]
        sys.path[:] = [entry for entry in sys.path if not _is_same_directory(entry=entry, directory=root)]
        importlib.invalidate_caches()


#: The process's one hold on a tree's Python.
TREE_PYTHON_HOLD = TreePythonHold()


def import_held_tree_module(*, identity: TreePythonIdentity, module_name: str) -> ModuleType:
    """Import a module of the held tree under its real name, and check that the import reached the tree.

    Args:
        identity: The held tree.
        module_name: The module's dotted import name.

    Returns:
        The imported module.

    Raises:
        TreePythonError: The tree is not held, or the import resolved to a module outside the tree, such as one
            imported under the same name before the tree loaded.
        ImportError: The module, or one it imports, cannot be imported; `TreeModuleExcludedError` for a file the tree
            excludes.
    """
    if not TREE_PYTHON_HOLD.is_held(identity=identity):
        msg = f"The Python of {identity.describe()} is not held, so its module '{module_name}' cannot be imported."
        raise TreePythonError(msg)
    module = importlib.import_module(module_name)
    location = _module_location(module=module)
    if location is None or not _is_under(path=location, directory=identity.root):
        msg = (
            f"The module '{module_name}' resolved to {location or 'a module with no file'}, outside {identity.describe()}: "
            "a module of that name was imported in this process before the tree's Python loaded."
        )
        raise TreePythonError(msg)
    return module
