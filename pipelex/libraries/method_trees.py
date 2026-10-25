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

A directory a host wrote a tree out as, and holds in `WRITTEN_METHOD_TREES`, is never listed: every listing of it returns
the tree as written, so the membership rule is not applied twice (`pipelex.libraries.written_trees`).

A listing hashes every file of the tree, and a file read from a listed tree afterwards is read against that hash
(`read_tree_file_as_listed`, `ensure_tree_files_as_listed`): a file edited, replaced or removed since the listing is
refused with `MethodTreeChangedError`, so a load never parses, and a run never reads, bytes other than those the tree's
digest names.
"""

import io
import os
import stat
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple, Protocol

from mthds.method_tree.digest import sha256_hex
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
    on_disk_name,
    read_directory,
)
from mthds.method_tree.exceptions import MethodTreeRefusedError, TreeLimitError, TreeSourceError
from mthds.method_tree.gitignore import PatternList
from mthds.method_tree.lister import hash_file, list_method_tree, list_method_tree_at_root
from mthds.method_tree.models import MethodTree, TreeFile, TreeLimits
from mthds.method_tree.tree_path import nfc
from mthds.method_tree.vocabulary import ExclusionRule, TreeRefusalCode

from pipelex import log
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.method_trees.method_file_store import HeldFile
from pipelex.core.method_trees.tree_bundle import TreeBundle
from pipelex.hosted.execution import get_or_load_pipelex_config
from pipelex.libraries.exceptions import (
    EmptyMethodTreeError,
    HostLibraryRequirementsError,
    HostLibraryTreeError,
    MethodRequirementsError,
    MethodTreeChangedError,
    MethodTreeLoadError,
)
from pipelex.libraries.written_trees import WRITTEN_METHOD_TREES

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
        EmptyMethodTreeError: The membership rule keeps every file of the directory out of its tree.
        MethodTreeLoadError: The standard refused the tree otherwise, it passed a limit, or it could not be read.
    """
    written = WRITTEN_METHOD_TREES.tree_written_at(directory=handed_over)
    if written is not None:
        return written
    try:
        return list_method_tree(handed_over, limits=limits or local_tree_limits())
    except TreeLimitError as exc:
        msg = f"{exc.message} {LIMITS_ADVICE}"
        raise MethodTreeLoadError(msg) from exc
    except MethodTreeRefusedError as exc:
        if _is_empty_tree(refusal_error=exc):
            raise EmptyMethodTreeError(exc.message) from exc
        raise _tree_refusal_error(refusal_error=exc, message=exc.message) from exc
    except TreeSourceError as exc:
        raise MethodTreeLoadError(exc.message) from exc


def list_local_method_tree_at_root(*, root: Path, limits: TreeLimits | None = None) -> MethodTree:
    """List the method tree rooted at a directory itself, with no Manifest Discovery, under this machine's limits.

    For a directory that is a method's root whatever lies above it, such as an entry of a corpus shipped inside an
    installed package, whose ancestors (a project above `site-packages`) may hold a `METHODS.toml` of their own.

    Raises:
        EmptyMethodTreeError: The membership rule keeps every file of the directory out of its tree.
        MethodTreeLoadError: The standard refused the tree otherwise, it passed a limit, or it could not be read.
    """
    written = WRITTEN_METHOD_TREES.tree_written_at(directory=root)
    if written is not None:
        return written
    try:
        return list_method_tree_at_root(root, limits=limits or local_tree_limits())
    except TreeLimitError as exc:
        msg = f"{exc.message} {LIMITS_ADVICE}"
        raise MethodTreeLoadError(msg) from exc
    except MethodTreeRefusedError as exc:
        if _is_empty_tree(refusal_error=exc):
            raise EmptyMethodTreeError(exc.message) from exc
        raise _tree_refusal_error(refusal_error=exc, message=exc.message) from exc
    except TreeSourceError as exc:
        raise MethodTreeLoadError(exc.message) from exc


def method_tree_root(*, handed_over: Path) -> Path:
    """The root of the method tree a folder handed over belongs to, resolved, found without listing the tree.

    The nearest directory at or above the folder holding a `METHODS.toml`, else the folder itself, as
    `list_local_method_tree` roots the tree it lists; the directory a host wrote a tree out as is that tree's root.

    Raises:
        MethodTreeLoadError: The folder cannot be resolved, or a directory on the way up cannot be looked into.
    """
    written = WRITTEN_METHOD_TREES.tree_written_at(directory=handed_over)
    if written is not None and written.directory is not None:
        return written.directory
    try:
        directory = handed_over.resolve(strict=True)
        return find_manifest_directory(directory) or directory
    except OSError as exc:
        msg = f"Cannot find the root of the method tree of '{handed_over}': {exc}"
        raise MethodTreeLoadError(msg) from exc
    except TreeSourceError as exc:
        raise MethodTreeLoadError(exc.message) from exc


def _tree_refusal_error(*, refusal_error: MethodTreeRefusedError, message: str, path_prefix: str = "") -> MethodTreeLoadError:
    """The `MethodTreeLoadError` of a tree the standard refused, giving `method.package_invalid` the facts it declares.

    Its `reason` is the standard's refusal code, such as `symbolic_link`, and its `path` the first tree path the refusal
    names, behind `path_prefix` (a dependency package's address, as the caller names that package's files), so a caller
    reads which rule the tree breaks and where without the message, which is the operator's.
    """
    error = MethodTreeLoadError(message)
    refusal = refusal_error.refusal
    if refusal.names:
        return error.with_params(reason=refusal.code, path=f"{path_prefix}{refusal.names[0]}")
    return error.with_params(reason=refusal.code)


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
    written = WRITTEN_METHOD_TREES.tree_written_at(directory=root)
    if written is not None:
        return written
    try:
        return list_method_tree_at_root(root, limits=limits or local_tree_limits())
    except MethodTreeRefusedError as exc:
        msg = _with_root_named(message=exc.message, root=root, label=package_address)
        raise _tree_refusal_error(refusal_error=exc, message=msg, path_prefix=f"{package_address}/") from exc
    except (TreeLimitError, TreeSourceError) as exc:
        msg = _with_root_named(message=exc.message, root=root, label=package_address)
        raise MethodTreeLoadError(msg) from exc


@contextmanager
def reporting_host_library_tree_faults() -> Generator[None, None, None]:
    """Report a method tree of this host's own library directories that cannot be listed, or whose requirements refuse it, as the host's fault.

    Around a load of library directories that are not the caller's, such as the ones a server loads beside a request's
    bundles, a `MethodTreeLoadError` leaves as a `HostLibraryTreeError`, and a `MethodRequirementsError` as a
    `HostLibraryRequirementsError`: both are configuration faults, whose messages, naming paths on the host, never reach
    the caller.

    Raises:
        HostLibraryTreeError: A tree of the directories could not be listed.
        HostLibraryRequirementsError: A method of the directories declares requirements its PipeFunc environment refuses.
    """
    try:
        yield
    except MethodTreeLoadError as exc:
        msg = f"A library directory of this host cannot be read as a method tree: {exc.message}"
        raise HostLibraryTreeError(msg) from exc
    except MethodRequirementsError as exc:
        msg = f"A library directory of this host holds a method whose requirements.txt refuses it: {exc.message}"
        raise HostLibraryRequirementsError(msg) from exc


def tree_bundles_of(*, tree: MethodTree) -> list[TreeBundle]:
    """The `.mthds` files of a tree, in tree path order, each as a member of the tree."""
    return [TreeBundle(tree=tree, tree_path=tree_path) for tree_path in tree.tree_paths if tree_path.endswith(BUNDLE_SUFFIX)]


def lone_file_member(*, tree: MethodTree, bundle_file: Path) -> TreeBundle:
    """A bundle file named alone as the member of the tree its listing returned, the entry that listing named for it.

    Raises:
        MethodTreeLoadError: The listing named no entry for the file: the membership rule keeps it out of its tree.
    """
    if tree.entry is None:
        msg = f"Listing the method tree of the bundle file '{bundle_file}' named no entry for it."
        raise MethodTreeLoadError(msg).with_params(reason=TreeRefusalCode.LONE_FILE_EXCLUDED)
    return TreeBundle(tree=tree, tree_path=tree.entry)


class HandedOverLocation(NamedTuple):
    """Where a path handed over as a method lies, read as the standard's lister reads it before it lists anything.

    A directory, a symbolic link naming one included, is named by its resolved path, and its tree is rooted at `root`.
    A `.mthds` file named alone is named by its folder resolved and its own name as the folder holds it, never followed,
    so a symbolic link named alone is a location of its own, which its listing refuses; its tree is rooted at `root`, its
    nearest `METHODS.toml`, or is its one-file tree when `root` is None.
    """

    directory: Path | None
    lone_file: Path | None
    root: Path | None


def locate_handed_over(*, handed_over: Path) -> HandedOverLocation | None:
    """Where a path handed over as a method lies, as `list_method_tree` reads it, or None when that reading fails.

    None is for a path the lister refuses before listing anything, one that does not exist or a file not named `.mthds`
    say: the caller lists it, and the lister gives the refusal.
    """
    try:
        status = os.lstat(handed_over)
        if stat.S_ISDIR(status.st_mode) or (stat.S_ISLNK(status.st_mode) and handed_over.is_dir()):
            directory = handed_over.resolve(strict=True)
            return HandedOverLocation(directory=directory, lone_file=None, root=find_manifest_directory(directory) or directory)
        parent = handed_over.absolute().parent.resolve(strict=True)
        lone_file = parent / on_disk_name(parent, handed_over.name)
        if not lone_file.name.endswith(BUNDLE_SUFFIX):
            return None
        return HandedOverLocation(directory=None, lone_file=lone_file, root=find_manifest_directory(parent))
    except (OSError, RuntimeError, TreeSourceError):
        return None


def lone_file_tree_path(*, root: Path, lone_file: Path) -> str | None:
    """The tree path of a lone file in the tree rooted at `root`, each name taken as the file system holds it, as the lister takes it.

    None when a name on the way cannot be read, for the caller to list the file and get the lister's own refusal.
    """
    current = root
    held_names: list[str] = []
    try:
        for part in lone_file.relative_to(root).parts:
            raw_name = on_disk_name(current, part)
            held_names.append(nfc(raw_name))
            current /= raw_name
    except (ValueError, TreeSourceError):
        return None
    return "/".join(held_names)


def _tree_label(*, tree: MethodTree) -> str:
    """How a message names a tree: by its root on this host, except a tree a host wrote out, whose root is the host's."""
    if tree.directory is None or WRITTEN_METHOD_TREES.holds_tree(tree=tree):
        return "the method tree"
    return f"the method tree at '{tree.directory}'"


def _changed_file_error(*, tree: MethodTree, tree_path: str, finding: str) -> MethodTreeChangedError:
    msg = (
        f"The file '{tree_path}' of {_tree_label(tree=tree)} {finding} since the tree was listed, so it is not the file the "
        "run listed and validated. Run again once the method's files stop changing."
    )
    return MethodTreeChangedError(msg).with_params(path=tree_path)


def _listed_file(*, tree: MethodTree, tree_path: str) -> TreeFile:
    """The listing's record of the file at `tree_path`.

    Raises:
        MethodTreeChangedError: The listing holds no such file.
    """
    for tree_file in tree.files:
        if tree_file.path == tree_path:
            return tree_file
    raise _changed_file_error(tree=tree, tree_path=tree_path, finding="is not a file of the tree as listed, or was added")


def read_tree_file_as_listed(*, tree: MethodTree, tree_path: str) -> bytes:
    """The bytes of a file of a tree listed from this host's disk, read now, refused unless they are the bytes its listing hashed.

    Raises:
        MethodTreeChangedError: The file is no longer there or cannot be read, or its bytes are not the ones listed.
    """
    listed = _listed_file(tree=tree, tree_path=tree_path)
    try:
        data = tree.file_location(tree_path).read_bytes()
    except OSError as exc:
        raise _changed_file_error(tree=tree, tree_path=tree_path, finding="was removed or became unreadable") from exc
    if len(data) != listed.size or sha256_hex(data) != listed.sha256:
        raise _changed_file_error(tree=tree, tree_path=tree_path, finding="changed")
    return data


def read_tree_bundle_as_listed(*, tree_bundle: TreeBundle) -> bytes:
    """The bytes of a bundle file of a listed tree, refused unless they are the bytes its listing hashed (`read_tree_file_as_listed`).

    Raises:
        MethodTreeChangedError: The bundle's file is no longer there or cannot be read, or its bytes are not the ones listed.
        PipelexUnexpectedError: The bundle is the one parsed from a string at a tree's root, which is no file of it.
    """
    if tree_bundle.tree_path is None:
        msg = "A bundle parsed from a string has no file of its method tree to read"
        raise PipelexUnexpectedError(msg)
    return read_tree_file_as_listed(tree=tree_bundle.tree, tree_path=tree_bundle.tree_path)


def decoded_as_text_file(*, data: bytes) -> str:
    """A file's bytes decoded as UTF-8 text is read from a file, each line ending made a newline (`Path.read_text`).

    Raises:
        UnicodeDecodeError: The bytes are not UTF-8.
    """
    return io.TextIOWrapper(io.BytesIO(data), encoding="utf-8").read()


def ensure_bundle_text_as_listed(*, tree_bundle: TreeBundle, mthds_content: str) -> None:
    """Refuse the text a caller read from a bundle file of a listed tree unless it is the text of the file the listing hashed.

    A caller that read the bundle's text itself, such as a CLI reading the bundle file it runs, read it at a moment of its
    own, before or after the tree's listing: the text is the bundle's only when it is the listed file's, decoded as the
    caller decoded it, with its line endings kept, or each made a newline as a text read makes them.

    Raises:
        MethodTreeChangedError: The bundle's file is no longer the one the listing hashed, or the text is not its text.
    """
    if tree_bundle.tree_path is None:
        return
    data = read_tree_file_as_listed(tree=tree_bundle.tree, tree_path=tree_bundle.tree_path)
    try:
        listed_text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _changed_file_error(tree=tree_bundle.tree, tree_path=tree_bundle.tree_path, finding="was read as text other than its own") from exc
    if mthds_content not in {listed_text, decoded_as_text_file(data=data)}:
        raise _changed_file_error(tree=tree_bundle.tree, tree_path=tree_bundle.tree_path, finding="changed")


def ensure_tree_files_as_listed(*, tree: MethodTree) -> None:
    """Read every file of a tree listed from this host's disk again, refusing the tree unless each is the file its listing hashed.

    A tree read from a map of file entries holds no file on this host, and is never read here.

    Raises:
        MethodTreeChangedError: A file is no longer there or cannot be read, or its bytes are not the ones listed.
    """
    if tree.directory is None:
        return
    for tree_file in tree.files:
        try:
            current = hash_file(tree.file_location(tree_file.path), tree_path=tree_file.path)
        except TreeSourceError as exc:
            raise _changed_file_error(tree=tree, tree_path=tree_file.path, finding="was removed or became unreadable") from exc
        if current.size != tree_file.size or current.sha256 != tree_file.sha256:
            raise _changed_file_error(tree=tree, tree_path=tree_file.path, finding="changed")


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
            | ExclusionRule.RUN_INPUTS
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


class LibraryDirTreeLister(Protocol):
    """Lists the tree a library directory is rooted in, or None when it is empty, as `list_library_dir_tree` does."""

    def __call__(self, *, library_dir: Path, limits: TreeLimits) -> MethodTree | None: ...


class LibraryTreesLister(Protocol):
    """Lists the trees a library directory holds, its own first, as `list_library_trees` does."""

    def __call__(self, *, library_dir: Path, limits: TreeLimits) -> list[MethodTree]: ...


def list_library_trees(*, library_dir: Path, limits: TreeLimits | None = None, own_tree_of: LibraryDirTreeLister | None = None) -> list[MethodTree]:
    """The method trees a library directory holds: its own, then those of the packages and repositories nested in it.

    A directory that does not exist holds none. One whose own tree the membership rule leaves empty, such as a
    directory holding nothing but nested methods, holds the trees nested in it.

    Args:
        library_dir: The library directory.
        limits: The limits to list each tree under, read from the configuration when not given.
        own_tree_of: How the tree the directory is rooted in is listed, such as through a run's listing, which holds it
            for every step of the run; `list_library_dir_tree` when not given.

    Raises:
        MethodTreeLoadError: A tree could not be listed.
    """
    if not library_dir.exists():
        log.debug(f"A library directory that does not exist was skipped: {library_dir}")
        return []
    active_limits = limits or local_tree_limits()
    own_tree = (own_tree_of or list_library_dir_tree)(library_dir=library_dir, limits=active_limits)
    return library_trees_from(library_dir=library_dir, own_tree=own_tree, limits=active_limits)


def list_library_dir_tree(*, library_dir: Path, limits: TreeLimits | None = None) -> MethodTree | None:
    """The method tree a library directory is rooted in, or None when the membership rule leaves it empty.

    The tree is rooted at the nearest `METHODS.toml` at or above the directory, else at the directory itself, as
    `list_local_method_tree` roots it, so a successful listing of either is the same tree; a directory a host wrote a
    tree out as returns the tree as written. An empty tree is no fault here: a library directory may hold nothing but
    nested methods, which `library_trees_from` finds.

    Args:
        library_dir: The library directory, which exists.
        limits: The limits to list the tree under, read from the configuration when not given.

    Raises:
        MethodTreeLoadError: The standard refused the tree for a reason other than its being empty, it passed a limit,
            or it could not be read.
    """
    written = WRITTEN_METHOD_TREES.tree_written_at(directory=library_dir)
    if written is not None:
        return written
    try:
        return list_method_tree(library_dir, limits=limits or local_tree_limits())
    except MethodTreeRefusedError as exc:
        if _is_empty_tree(refusal_error=exc):
            return None
        raise MethodTreeLoadError(exc.message) from exc
    except TreeLimitError as exc:
        msg = f"{exc.message} {LIMITS_ADVICE}"
        raise MethodTreeLoadError(msg) from exc
    except TreeSourceError as exc:
        raise MethodTreeLoadError(exc.message) from exc


def library_trees_from(*, library_dir: Path, own_tree: MethodTree | None, limits: TreeLimits) -> list[MethodTree]:
    """The method trees a library directory holds, from the tree it is rooted in, as `list_library_dir_tree` listed it.

    That tree comes first, then the tree of each package and repository nested in it, and theirs, depth first. A tree a
    host wrote out holds no nested tree, since reading it back as written keeps nothing out: so the answer depends on the
    tree alone, never on whether its writer still holds it. A directory whose own tree is empty (`own_tree` None) holds
    the trees nested in it.

    Raises:
        MethodTreeLoadError: A nested tree could not be listed.
    """
    if own_tree is None:
        return _trees_nested_in_empty_directory(directory=library_dir.resolve(), limits=limits)
    return _library_trees(tree=own_tree, limits=limits)


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


class LibraryTree(NamedTuple):
    """A method tree a library directory holds, with the directory as the caller gave it."""

    library_dir: Path
    tree: MethodTree


def list_library_dir_trees(
    *, library_dirs: Iterable[Path], limits: TreeLimits | None = None, trees_of: LibraryTreesLister | None = None
) -> list[LibraryTree]:
    """The method trees of the library directories, in the order the directories are given, each directory's own first.

    A tree holding no bundle is listed too, such as one holding only the Python a server received beside a method's
    bundles: a load reads its `requirements.txt` before it reads any of its Python.

    Args:
        library_dirs: The library directories.
        limits: The limits to list each tree under, read from the configuration once when not given.
        trees_of: How a directory's trees are listed, such as through a run's listing; `list_library_trees` when not given.

    Raises:
        MethodTreeLoadError: A tree could not be listed.
    """
    active_limits = limits or local_tree_limits()
    library_trees: list[LibraryTree] = []
    for library_dir in library_dirs:
        for tree in (trees_of or list_library_trees)(library_dir=library_dir, limits=active_limits):
            library_trees.append(LibraryTree(library_dir=library_dir, tree=tree))
    return library_trees


def library_bundle_files_of(*, library_trees: Iterable[LibraryTree]) -> list[LibraryBundleFile]:
    """The bundle files of listed library trees, each as a member of its method tree, each file once.

    A file two of the trees hold, such as a directory and one of its subdirectories both given, is the member of the
    first tree that holds it, spelled from that tree's library directory.
    """
    seen_locations: set[Path] = set()
    bundle_files: list[LibraryBundleFile] = []
    for library_tree in library_trees:
        for tree_bundle in tree_bundles_of(tree=library_tree.tree):
            location = tree_bundle.location
            if location in seen_locations:
                continue
            seen_locations.add(location)
            spelled_path = _spelled_from(library_dir=library_tree.library_dir, location=location)
            bundle_files.append(LibraryBundleFile(tree_bundle=tree_bundle, path=spelled_path))
    return bundle_files


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
    return library_bundle_files_of(library_trees=list_library_dir_trees(library_dirs=library_dirs, limits=limits))


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


def _spelling_prefix(*, tree_root: Path, library_dir: Path) -> tuple[str, str] | None:
    """How a tree path is spelled from a library directory, as `(stripped, added)` prefixes, or None when they share nothing.

    A tree rooted at the directory spells its paths as they are; one nested in it adds the tree's folder; one rooted above
    it, at a `METHODS.toml`, strips the directory's folder from the paths lying in it.
    """
    if tree_root == library_dir:
        return ("", "")
    if tree_root.is_relative_to(library_dir):
        return ("", f"{nfc(tree_root.relative_to(library_dir).as_posix())}/")
    if library_dir.is_relative_to(tree_root):
        return (f"{nfc(library_dir.relative_to(tree_root).as_posix())}/", "")
    return None


def tree_python_sources(*, tree: MethodTree, library_dir: Path | None) -> dict[str, str]:
    """The text of every Python file of a tree listed from this host's disk, keyed by its path from the library directory.

    A file outside the library directory, or of a tree that no library directory holds, such as the tree of a bundle file
    named alone, is keyed by its tree path: the key names the file to a caller, never by a path of this host. These are
    the sources a sandbox-hosted load scans for structure classes without importing them, so a file that is not UTF-8
    text is read with replacement characters. Each is read against the hash its listing recorded.

    Raises:
        MethodTreeChangedError: A Python file is not the one the tree's listing hashed.
    """
    if tree.directory is None:
        return {}
    spelling = _spelling_prefix(tree_root=tree.directory.resolve(), library_dir=library_dir.resolve()) if library_dir is not None else None
    sources: dict[str, str] = {}
    for tree_path in tree.tree_paths:
        if not tree_path.endswith(".py"):
            continue
        key = tree_path
        if spelling is not None and tree_path.startswith(spelling[0]):
            key = f"{spelling[1]}{tree_path.removeprefix(spelling[0])}"
        sources[key] = read_tree_file_as_listed(tree=tree, tree_path=tree_path).decode("utf-8", errors="replace")
    return sources


def listing_identity(*, tree: MethodTree) -> tuple[str, str, bool]:
    """What makes two listings one tree on this host: their root, their digest, and whether they are a one-file tree.

    Two listings of one directory with the same files are one tree, and a one-file tree is never the directory tree of
    its folder, since only the latter lets a reference reach another file. A crate needs none of this: it names a tree by
    its digest alone, which names its files' bytes wherever they lie.
    """
    return (str(tree.directory), tree.digest, tree.is_one_file)


def submitted_tree_files(*, library_tree: LibraryTree) -> dict[str, HeldFile]:
    """The files a library directory submits beside bundles parsed from content strings, keyed by their path from it.

    A directory whose own tree holds no bundle, such as the directory a server writes a request's files into beside the
    request's bundles, is where those bundles' references and import paths start, so its files join the tree of the files
    submitted with them, the bundles sitting at its root. A tree holding a bundle submits nothing: its steps read and
    call their own tree's files, so a directory's files never join two trees. Neither does a tree nested in a library
    directory. The membership rule decides what the tree holds, so a `.gitignore`d file or a virtual environment never
    joins. Nothing is read: each file is held by the hash its listing recorded, and read from the disk when it is used.

    Args:
        library_tree: A tree the library directory holds, as `list_library_dir_trees` listed it.
    """
    tree = library_tree.tree
    if tree.directory is None or any(tree_path.endswith(BUNDLE_SUFFIX) for tree_path in tree.tree_paths):
        return {}
    spelling = _spelling_prefix(tree_root=tree.directory.resolve(), library_dir=library_tree.library_dir.resolve())
    if spelling is None or spelling[1]:
        # Not the directory's own tree: one nested in it.
        return {}
    stripped_prefix = spelling[0]
    files: dict[str, HeldFile] = {}
    for tree_file in tree.files:
        if tree_file.path.startswith(stripped_prefix):
            files[tree_file.path.removeprefix(stripped_prefix)] = HeldFile(
                sha256=tree_file.sha256, size=tree_file.size, source=tree.file_location(tree_file.path)
            )
    return files
