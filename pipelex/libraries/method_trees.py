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

Each tree is listed under `[interpreter.method_tree_limits]`, this machine's own limits: the lister stops before
hashing any file once a tree passes one, so a directory handed over by mistake is refused in moments.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from mthds.method_tree.discovery import BUNDLE_SUFFIX
from mthds.method_tree.exceptions import MethodTreeRefusedError, TreeLimitError, TreeSourceError
from mthds.method_tree.lister import list_method_tree, list_method_tree_at_root
from mthds.method_tree.models import MethodTree, TreeLimits
from mthds.method_tree.vocabulary import ExclusionRule, TreeRefusalCode

from pipelex import log
from pipelex.core.method_trees.tree_bundle import TreeBundle
from pipelex.hosted.execution import get_or_load_pipelex_config
from pipelex.libraries.exceptions import MethodTreeLoadError

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


def list_local_method_tree(*, handed_over: Path) -> MethodTree:
    """List the method tree of a directory, or of a `.mthds` file named alone, under this machine's limits.

    Raises:
        MethodTreeLoadError: The standard refused the tree, it passed a limit, or it could not be read.
    """
    try:
        return list_method_tree(handed_over, limits=local_tree_limits())
    except TreeLimitError as exc:
        msg = f"{exc.message} {LIMITS_ADVICE}"
        raise MethodTreeLoadError(msg) from exc
    except (MethodTreeRefusedError, TreeSourceError) as exc:
        raise MethodTreeLoadError(exc.message) from exc


def list_local_method_tree_at_root(*, root: Path) -> MethodTree:
    """List the tree rooted at `root` itself, as a dependency package's tree is, under this machine's limits.

    Raises:
        MethodTreeLoadError: The standard refused the tree, it passed a limit, or it could not be read.
    """
    try:
        return list_method_tree_at_root(root, limits=local_tree_limits())
    except TreeLimitError as exc:
        msg = f"{exc.message} {LIMITS_ADVICE}"
        raise MethodTreeLoadError(msg) from exc
    except (MethodTreeRefusedError, TreeSourceError) as exc:
        raise MethodTreeLoadError(exc.message) from exc


def tree_bundles_of(*, tree: MethodTree) -> list[TreeBundle]:
    """The `.mthds` files of a tree, in tree path order, each as a member of the tree."""
    return [TreeBundle(tree=tree, tree_path=tree_path) for tree_path in tree.tree_paths if tree_path.endswith(BUNDLE_SUFFIX)]


def tree_bundle_of_lone_file(*, bundle_file: Path) -> TreeBundle:
    """A bundle file this host read, named alone, as the member of its method tree.

    Its tree is rooted at the nearest `METHODS.toml` at or above its folder, else it is the one-file tree of the file,
    from which a reference to any other file is refused.

    Raises:
        MethodTreeLoadError: The tree could not be listed, or the membership rule keeps the file out of it.
    """
    tree = list_local_method_tree(handed_over=bundle_file)
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


def _library_trees(*, tree: MethodTree) -> list[MethodTree]:
    """`tree`, then the tree of each nested package and nested repository it kept out, and theirs, depth first."""
    trees = [tree]
    if tree.directory is None:
        return trees
    for tree_path, exclusion in tree.excluded_directories.items():
        if not _holds_a_tree_of_its_own(rule=exclusion.rule):
            continue
        on_disk = tree.raw_paths.get(tree_path, tree_path)
        nested_root = tree.directory.joinpath(*on_disk.split("/"))
        try:
            nested_tree = list_local_method_tree_at_root(root=nested_root)
        except MethodTreeLoadError as exc:
            if isinstance(exc.__cause__, MethodTreeRefusedError) and _is_empty_tree(refusal_error=exc.__cause__):
                continue
            raise
        trees.extend(_library_trees(tree=nested_tree))
    return trees


def list_library_trees(*, library_dir: Path) -> list[MethodTree]:
    """The method trees a library directory holds: its own, then those of the packages and repositories nested in it.

    A directory that does not exist holds none, and neither does one whose tree the membership rule leaves empty.

    Raises:
        MethodTreeLoadError: A tree could not be listed.
    """
    if not library_dir.exists():
        log.debug(f"A library directory that does not exist was skipped: {library_dir}")
        return []
    try:
        tree = list_method_tree(library_dir, limits=local_tree_limits())
    except MethodTreeRefusedError as exc:
        if _is_empty_tree(refusal_error=exc):
            log.debug(f"A library directory holding no file of a method tree was skipped: {library_dir}")
            return []
        raise MethodTreeLoadError(exc.message) from exc
    except TreeLimitError as exc:
        msg = f"{exc.message} {LIMITS_ADVICE}"
        raise MethodTreeLoadError(msg) from exc
    except TreeSourceError as exc:
        raise MethodTreeLoadError(exc.message) from exc
    return _library_trees(tree=tree)


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


def list_library_bundle_files(*, library_dirs: Iterable[Path]) -> list[LibraryBundleFile]:
    """The bundle files of the library directories, each as a member of its method tree, each file once.

    The directories are read in the order given, and a file two of their trees hold, such as a directory and one of
    its subdirectories both given, is the member of the first tree that holds it.

    Raises:
        MethodTreeLoadError: A tree could not be listed.
    """
    seen_locations: set[Path] = set()
    bundle_files: list[LibraryBundleFile] = []
    for library_dir in library_dirs:
        for tree in list_library_trees(library_dir=library_dir):
            for tree_bundle in tree_bundles_of(tree=tree):
                location = tree_bundle.location
                if location in seen_locations:
                    continue
                seen_locations.add(location)
                bundle_files.append(LibraryBundleFile(tree_bundle=tree_bundle, path=_spelled_from(library_dir=library_dir, location=location)))
    return bundle_files
