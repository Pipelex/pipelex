"""Listing the method trees a local load reads its bundles from, under this machine's limits.

Every bundle this host reads from its own disk is read as a member of a method tree, listed by `mthds-python`
(`mthds/docs/spec/method-tree.md`): the tree a directory is rooted in, at the nearest `METHODS.toml` at or above it,
else at the directory itself; the tree of a `.mthds` file named alone, rooted at the nearest `METHODS.toml` at or
above its folder, else the one-file tree of that file; and a dependency package's tree, rooted at the package's own
directory. The membership rule decides what a tree holds, so a file it keeps out, a dotfile, a `.gitignore`d file, a
virtual environment, is never loaded and never read by a step.

A library directory, such as a `-L` directory or one of `PIPELEXPATH`, is not a method but a place methods are
found: its own tree is loaded, then each nested package and nested repository the listing kept out of it, each as a
tree of its own, so every method under it loads as it did before trees, and each reads only its own files.

A package or repository nested in a library directory that holds no `.mthds` file is skipped before it is listed, so
a nested checkout with nothing to load, a submodule say, never fails the load for a file it holds. A library directory
whose own tree is empty, one holding nothing but nested methods, still has its nested methods found and loaded.

Each tree is listed under `[interpreter.method_tree_limits]`, this machine's own limits, read once per load: the lister
stops before hashing any file once a tree passes one, so a directory handed over by mistake is refused in moments.
"""

from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from mthds.method_tree.discovery import (
    BUNDLE_SUFFIX,
    DEFAULT_DIRECTORY_NAMES,
    GITIGNORE_NAME,
    DirectoryEntry,
    find_manifest_directory,
    holds_git_entry,
    holds_manifest,
    holds_venv_marker,
    kind_of_exact_name,
    read_directory,
)
from mthds.method_tree.exceptions import MethodTreeRefusedError, TreeLimitError, TreeSourceError
from mthds.method_tree.gitignore import PatternList
from mthds.method_tree.lister import list_method_tree, list_method_tree_at_root
from mthds.method_tree.models import MethodTree, TreeLimits
from mthds.method_tree.tree_path import nfc
from mthds.method_tree.vocabulary import ExclusionRule, TreeRefusalCode

from pipelex import log
from pipelex.core.method_trees.tree_bundle import TreeBundle
from pipelex.hosted.execution import get_or_load_pipelex_config
from pipelex.libraries.exceptions import HostLibraryTreeError, MethodTreeLoadError

LIMITS_ADVICE = (
    "Hand over the method's own folder rather than a directory above it, or raise the limits of "
    "interpreter.method_tree_limits in your project's .pipelex/pipelex.toml."
)


def local_tree_limits() -> TreeLimits:
    """The limits this machine lists a method tree under, from `[interpreter.method_tree_limits]`.

    Read from the booted configuration, or from the configuration files when nothing booted, since a CLI lists the
    tree it runs before it boots, and a hosted run never boots.

    Raises:
        PipelexConfigError: If nothing booted and the configuration files do not validate.
    """
    limits_config = get_or_load_pipelex_config().interpreter.method_tree_limits
    return TreeLimits(
        max_files=limits_config.max_files,
        max_total_bytes=limits_config.max_total_bytes,
        max_file_bytes=limits_config.max_file_bytes,
    )


def list_local_method_tree(*, handed_over: Path, limits: TreeLimits | None = None) -> MethodTree:
    """List the method tree of a directory, or of a `.mthds` file named alone, under this machine's limits.

    Args:
        handed_over: The directory or the `.mthds` file handed over.
        limits: The limits to list under, read from the configuration when not given.

    Raises:
        MethodTreeLoadError: The standard refused the tree, it passed a limit, or it could not be read.
    """
    try:
        return list_method_tree(handed_over, limits=limits or local_tree_limits())
    except TreeLimitError as exc:
        msg = f"{exc.message} {LIMITS_ADVICE}"
        raise MethodTreeLoadError(msg) from exc
    except (MethodTreeRefusedError, TreeSourceError) as exc:
        raise MethodTreeLoadError(exc.message) from exc


def _with_root_named(*, message: str, root: Path, label: str) -> str:
    """`message` with every spelling of `root` it holds replaced by `label`, the longest spelling first."""
    spellings = {str(root), str(root.absolute())}
    try:
        spellings.add(str(root.resolve()))
    except (OSError, RuntimeError):
        pass
    for spelling in sorted(spellings, key=len, reverse=True):
        message = message.replace(spelling, label)
    return message


def list_package_method_tree(*, root: Path, package_address: str, limits: TreeLimits | None = None) -> MethodTree:
    """List a dependency package's tree, rooted at the package's own directory, under this machine's limits.

    A refusal names the package by its address and its files by their tree paths, never by the directory the package
    was installed or fetched into, which is a path on this host: the package is the caller's dependency, so the refusal
    is theirs to read, and nothing in it is theirs to change on this host, so it gives no advice about its limits.

    Raises:
        MethodTreeLoadError: The standard refused the tree, it passed a limit, or it could not be read.
    """
    try:
        return list_method_tree_at_root(root, limits=limits or local_tree_limits())
    except (MethodTreeRefusedError, TreeLimitError, TreeSourceError) as exc:
        msg = _with_root_named(message=exc.message, root=root, label=package_address)
        raise MethodTreeLoadError(msg) from exc


@contextmanager
def reporting_host_library_tree_faults() -> Generator[None, None, None]:
    """Report a method tree of this host's own library directories that cannot be listed as the host's fault.

    Around a load of library directories that are not the caller's, such as the ones a server loads beside a request's
    bundles, a `MethodTreeLoadError` leaves as a `HostLibraryTreeError`, which is a configuration fault and whose
    message, naming paths on the host, never reaches the caller.

    Raises:
        HostLibraryTreeError: A tree of the directories could not be listed.
    """
    try:
        yield
    except MethodTreeLoadError as exc:
        msg = f"A library directory of this host cannot be read as a method tree: {exc.message}"
        raise HostLibraryTreeError(msg) from exc


def tree_bundles_of(*, tree: MethodTree) -> list[TreeBundle]:
    """The `.mthds` files of a tree, in tree path order, each as a member of the tree."""
    return [TreeBundle(tree=tree, tree_path=tree_path) for tree_path in tree.tree_paths if tree_path.endswith(BUNDLE_SUFFIX)]


def tree_bundle_of_lone_file(*, bundle_file: Path, limits: TreeLimits | None = None) -> TreeBundle:
    """A bundle file this host read, named alone, as the member of its method tree.

    Its tree is rooted at the nearest `METHODS.toml` at or above its folder, else it is the one-file tree of the file,
    from which a reference to any other file is refused.

    Raises:
        MethodTreeLoadError: The tree could not be listed, or the membership rule keeps the file out of it.
    """
    tree = list_local_method_tree(handed_over=bundle_file, limits=limits)
    if tree.entry is None:
        msg = f"Listing the method tree of the bundle file '{bundle_file}' named no entry for it."
        raise MethodTreeLoadError(msg)
    return TreeBundle(tree=tree, tree_path=tree.entry)


def _is_empty_tree(*, refusal_error: MethodTreeRefusedError) -> bool:
    match refusal_error.refusal.code:
        case TreeRefusalCode.EMPTY_TREE:
            return True
        case (
            TreeRefusalCode.SYMBOLIC_LINK
            | TreeRefusalCode.SPECIAL_FILE
            | TreeRefusalCode.INVALID_TREE_PATH
            | TreeRefusalCode.NORMALIZATION_COLLISION
            | TreeRefusalCode.PATH_COLLISION
            | TreeRefusalCode.LONE_FILE_EXCLUDED
            | TreeRefusalCode.GITIGNORE_NOT_UTF8
            | TreeRefusalCode.DUPLICATE_KEY
            | TreeRefusalCode.EXCLUDED_NAME
            | TreeRefusalCode.MALFORMED_ENTRY
            | TreeRefusalCode.MISSING_BLOB
            | TreeRefusalCode.REFERENCE_INVALID
            | TreeRefusalCode.REFERENCE_LEAVES_TREE
            | TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH
            | TreeRefusalCode.REFERENCE_NOT_IN_TREE
            | TreeRefusalCode.REFERENCE_IN_ONE_FILE_TREE
            | TreeRefusalCode.FUNCTION_NAME_WITHOUT_MODULE
            | TreeRefusalCode.FUNCTION_NAME_INVALID_SEGMENT
            | TreeRefusalCode.MODULE_NOT_IN_TREE
            | TreeRefusalCode.MODULE_AMBIGUOUS
        ):
            return False


def _holds_a_tree_of_its_own(*, rule: ExclusionRule) -> bool:
    """Whether a directory a library directory's listing kept out by `rule` is a tree of its own, loaded beside it."""
    match rule:
        case ExclusionRule.NESTED_PACKAGE | ExclusionRule.NESTED_REPOSITORY:
            return True
        case (
            ExclusionRule.DOT_SEGMENT
            | ExclusionRule.PYCACHE_OR_NODE_MODULES
            | ExclusionRule.VIRTUAL_ENVIRONMENT
            | ExclusionRule.GITIGNORE
            | ExclusionRule.PACKAGE_EXCLUDE
        ):
            return False


def _holds_a_bundle_name(*, directory: Path) -> bool:
    """Whether any file under `directory` is named like a bundle, judged by names alone, before any tree is listed.

    A cheap scan: it skips what the membership rule keeps out by name (a dot segment, `__pycache__` and
    `node_modules`, a virtual environment) and reads no `.gitignore`, so it may find a bundle a listing then keeps out,
    never miss one a listing keeps. A directory it cannot read holds nothing it can find.
    """
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            entries = read_directory(current)
        except OSError:
            continue
        if holds_venv_marker(entries):
            continue
        for entry in entries:
            if entry.raw_name.startswith("."):
                continue
            if entry.kind.is_directory:
                if entry.raw_name not in DEFAULT_DIRECTORY_NAMES:
                    pending.append(current / entry.raw_name)
            elif entry.raw_name.endswith(BUNDLE_SUFFIX):
                return True
    return False


def _with_gitignore(
    *, location: Path, tree_path: str, entries: list[DirectoryEntry], pattern_lists: tuple[PatternList, ...]
) -> tuple[PatternList, ...]:
    """The pattern lists that apply to a directory's entries: its parents', and its own `.gitignore` file's when it holds one."""
    kind = kind_of_exact_name(entries, GITIGNORE_NAME)
    if kind is None or not kind.is_regular_file:
        return pattern_lists
    try:
        pattern_list = PatternList.make_from_bytes((location / GITIGNORE_NAME).read_bytes(), base=tree_path)
    except (OSError, UnicodeDecodeError):
        # The listing that found this tree empty read the file; one that changed since keeps nothing out.
        return pattern_lists
    return (*pattern_lists, pattern_list)


def _kept_out_by_patterns(*, tree_path: str, pattern_lists: tuple[PatternList, ...]) -> bool:
    """Whether the `.gitignore` patterns keep a directory out, as git decides: the deepest file with a matching pattern."""
    for pattern_list in reversed(pattern_lists):
        matched = pattern_list.last_match(tree_path, is_dir=True)
        if matched is not None:
            return not matched.negative
    return False


def _nested_tree_roots(*, directory: Path) -> list[Path]:
    """The roots of the packages and repositories nested in a directory whose own tree the membership rule leaves empty.

    The lister refuses an empty tree without saying what it kept out, so this walks the directory as the lister does,
    judging each directory by its name, then by its own entries, then by the `.gitignore` patterns, and descends into
    every directory it keeps: a nested package or repository is a root, and what the rule keeps out is never entered.
    The tree is rooted at the directory itself, since a tree rooted at a `METHODS.toml` holds that file and is never empty.
    """
    roots: list[Path] = []
    pending: list[tuple[Path, str, tuple[PatternList, ...]]] = [(directory, "", ())]
    while pending:
        location, tree_path, parent_pattern_lists = pending.pop()
        try:
            entries = read_directory(location)
        except OSError:
            continue
        pattern_lists = _with_gitignore(location=location, tree_path=tree_path, entries=entries, pattern_lists=parent_pattern_lists)
        children: list[tuple[Path, str, tuple[PatternList, ...]]] = []
        for entry in sorted(entries, key=lambda directory_entry: directory_entry.raw_name):
            name = nfc(entry.raw_name)
            if not entry.kind.is_directory or name.startswith(".") or name in DEFAULT_DIRECTORY_NAMES:
                continue
            child_location = location / entry.raw_name
            child_tree_path = f"{tree_path}/{name}" if tree_path else name
            try:
                child_entries = read_directory(child_location)
            except OSError:
                continue
            if holds_venv_marker(child_entries):
                continue
            if holds_git_entry(child_entries) or holds_manifest(child_entries):
                roots.append(child_location)
                continue
            if _kept_out_by_patterns(tree_path=child_tree_path, pattern_lists=pattern_lists):
                continue
            children.append((child_location, child_tree_path, pattern_lists))
        pending.extend(reversed(children))
    return roots


def _trees_nested_in_empty_directory(*, directory: Path, limits: TreeLimits) -> list[MethodTree]:
    """The trees of the packages and repositories nested in a directory whose own tree is empty, and theirs."""
    trees: list[MethodTree] = []
    for nested_root in _nested_tree_roots(directory=directory):
        trees.extend(_nested_library_trees(root=nested_root, limits=limits))
    return trees


def _nested_library_trees(*, root: Path, limits: TreeLimits) -> list[MethodTree]:
    """The tree of a package or repository nested in a library directory, then the trees nested in it, depth first.

    One that holds no file named like a bundle is skipped before it is listed, so a nested checkout with nothing to
    load never refuses the load for a file it holds; one that does follows every rule of the standard.

    Raises:
        MethodTreeLoadError: A tree could not be listed.
    """
    if not _holds_a_bundle_name(directory=root):
        log.debug(f"A nested directory holding no bundle was skipped: {root}")
        return []
    try:
        tree = list_method_tree_at_root(root, limits=limits)
    except MethodTreeRefusedError as exc:
        if _is_empty_tree(refusal_error=exc):
            return _trees_nested_in_empty_directory(directory=root, limits=limits)
        raise MethodTreeLoadError(exc.message) from exc
    except TreeLimitError as exc:
        msg = f"{exc.message} {LIMITS_ADVICE}"
        raise MethodTreeLoadError(msg) from exc
    except TreeSourceError as exc:
        raise MethodTreeLoadError(exc.message) from exc
    return _library_trees(tree=tree, limits=limits)


def _library_trees(*, tree: MethodTree, limits: TreeLimits) -> list[MethodTree]:
    """`tree`, then the tree of each nested package and nested repository it kept out, and theirs, depth first."""
    trees = [tree]
    if tree.directory is None:
        return trees
    for tree_path, exclusion in tree.excluded_directories.items():
        if not _holds_a_tree_of_its_own(rule=exclusion.rule):
            continue
        on_disk = tree.raw_paths.get(tree_path, tree_path)
        trees.extend(_nested_library_trees(root=tree.directory.joinpath(*on_disk.split("/")), limits=limits))
    return trees


def list_library_trees(*, library_dir: Path, limits: TreeLimits | None = None) -> list[MethodTree]:
    """The method trees a library directory holds: its own, then those of the packages and repositories nested in it.

    A directory that does not exist holds none. One whose own tree the membership rule leaves empty, such as a
    directory holding nothing but nested methods, holds the trees nested in it.

    Args:
        library_dir: The library directory.
        limits: The limits to list each tree under, read from the configuration when not given.

    Raises:
        MethodTreeLoadError: A tree could not be listed.
    """
    if not library_dir.exists():
        log.debug(f"A library directory that does not exist was skipped: {library_dir}")
        return []
    active_limits = limits or local_tree_limits()
    try:
        tree = list_method_tree(library_dir, limits=active_limits)
    except MethodTreeRefusedError as exc:
        if _is_empty_tree(refusal_error=exc):
            return _trees_nested_in_empty_directory(directory=library_dir.resolve(), limits=active_limits)
        raise MethodTreeLoadError(exc.message) from exc
    except TreeLimitError as exc:
        msg = f"{exc.message} {LIMITS_ADVICE}"
        raise MethodTreeLoadError(msg) from exc
    except TreeSourceError as exc:
        raise MethodTreeLoadError(exc.message) from exc
    return _library_trees(tree=tree, limits=active_limits)


class LibraryBundleFile(NamedTuple):
    """A bundle file of a library directory: the member of its method tree, and its path spelled from the directory as given."""

    tree_bundle: TreeBundle
    path: Path


def _spelled_from(*, library_dir: Path, location: Path) -> Path:
    """`location` spelled from `library_dir` as the caller gave it, so a relative library directory names relative files.

    A file outside the directory, in a tree rooted above it at a `METHODS.toml`, keeps its absolute path.
    """
    try:
        return library_dir / location.relative_to(library_dir.resolve())
    except ValueError:
        return location


def list_library_bundle_files(*, library_dirs: Iterable[Path], limits: TreeLimits | None = None) -> list[LibraryBundleFile]:
    """The bundle files of the library directories, each as a member of its method tree, each file once.

    The directories are read in the order given, and a file two of their trees hold, such as a directory and one of
    its subdirectories both given, is the member of the first tree that holds it.

    Args:
        library_dirs: The library directories.
        limits: The limits to list each tree under, read from the configuration once when not given.

    Raises:
        MethodTreeLoadError: A tree could not be listed.
    """
    active_limits = limits or local_tree_limits()
    seen_locations: set[Path] = set()
    bundle_files: list[LibraryBundleFile] = []
    for library_dir in library_dirs:
        for tree in list_library_trees(library_dir=library_dir, limits=active_limits):
            for tree_bundle in tree_bundles_of(tree=tree):
                location = tree_bundle.location
                if location in seen_locations:
                    continue
                seen_locations.add(location)
                bundle_files.append(LibraryBundleFile(tree_bundle=tree_bundle, path=_spelled_from(library_dir=library_dir, location=location)))
    return bundle_files


def bundle_files_under(*, library_dirs: Iterable[Path]) -> list[Path]:
    """Every `.mthds` file under the library directories and the trees they are rooted in, whatever the membership rule.

    Never raises: it is for a caller that must name every file a load of the directories could have named even when
    listing their trees fails, such as one withholding a host's files from a verdict, so it returns a superset of the
    files a load names, spelled from each directory as given.
    """
    bundle_files: list[Path] = []
    for library_dir in library_dirs:
        try:
            tree_root = find_manifest_directory(library_dir.resolve()) or library_dir
        except (OSError, RuntimeError, TreeSourceError):
            tree_root = library_dir
        for search_root in dict.fromkeys((library_dir, tree_root)):
            try:
                bundle_files.extend(sorted(search_root.rglob(f"*{BUNDLE_SUFFIX}")))
            except OSError:
                continue
    return list(dict.fromkeys(bundle_files))


def library_dir_call_files(*, library_dir: Path, limits: TreeLimits | None = None) -> dict[str, bytes]:
    """The files of a library directory's own method tree that lie in the directory, other than its bundles.

    These are the files a sandbox-hosted deployment sends with a `PipeFunc` call of a bundle parsed from a content
    string, keyed by their path from the library directory, which is where such a bundle's import paths start. The
    membership rule decides what the tree holds, so a `.gitignore`d file or a virtual environment never travels. A
    directory that does not exist, or whose own tree is empty, holds none.

    Args:
        library_dir: The library directory.
        limits: The limits to list the tree under, read from the configuration when not given.

    Raises:
        MethodTreeLoadError: The tree could not be listed.
    """
    if not library_dir.exists():
        return {}
    try:
        tree = list_method_tree(library_dir, limits=limits or local_tree_limits())
    except MethodTreeRefusedError as exc:
        if _is_empty_tree(refusal_error=exc):
            return {}
        raise MethodTreeLoadError(exc.message) from exc
    except TreeLimitError as exc:
        msg = f"{exc.message} {LIMITS_ADVICE}"
        raise MethodTreeLoadError(msg) from exc
    except TreeSourceError as exc:
        raise MethodTreeLoadError(exc.message) from exc
    if tree.directory is None:
        return {}
    resolved_dir = library_dir.resolve()
    tree_root = tree.directory.resolve()
    prefix = "" if resolved_dir == tree_root else f"{nfc(resolved_dir.relative_to(tree_root).as_posix())}/"
    files: dict[str, bytes] = {}
    for tree_path in tree.tree_paths:
        if not tree_path.startswith(prefix) or tree_path.endswith(BUNDLE_SUFFIX):
            continue
        files[tree_path.removeprefix(prefix)] = tree.file_location(tree_path).read_bytes()
    return files
