"""How every CLI command taking a bundle path reads it: a `.mthds` file, or a method's folder.

`run bundle`, `validate bundle`, `fix bundle`, `pipelex-agent inputs bundle`, `pipelex build inputs bundle` and
`pipelex build output bundle`, on both CLIs, read their target here, so the same arguments name the same method on every
command:

- A folder is the method rooted at the nearest `METHODS.toml` at or above it, else at the folder itself, listed as its
  method tree under this machine's limits (`[interpreter.method_tree_limits]`). The folder joins the library
  directories, ahead of `-L`. What a command reads of it depends on what the command does (`FolderReading`):
    - A command acting on one pipe, `run`, `inputs` and `build`, acts on the pipe named, else on the pipe the MTHDS
      protocol says a run naming no pipe starts at (`pipelex.pipeline.method_entry`): the manifest's `main_pipe`, else
      the one `main_pipe` its bundles declare; none or several is refused, the bundles named by their tree paths.
    - A command judging the method, `validate` and `fix`, reads the whole tree, every bundle of it, as the protocol's
      validation does, and so needs no pipe to start at.
- A `.mthds` file named alone is the member of its own file's tree (see `list_bundle_file_tree`), and acts on its own
  `main_pipe` unless a pipe is named.

The tree is listed once, through a `MethodTreeListing` the command hands down to its load
(`pipelex.libraries.method_tree_listing`): the load takes the tree from it rather than listing the folder or the file
again, so the tree whose digest a run records is the tree it loaded.

The shared core decides; each command renders the refusals as its own surface renders them.
"""

from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

from mthds.method_tree.discovery import BUNDLE_SUFFIX
from mthds.method_tree.models import MethodTree
from mthds.protocol.problem.registry import CoreCode

from pipelex.libraries.exceptions import EmptyMethodTreeError, MethodTreeLoadError
from pipelex.libraries.method_tree_listing import MethodTreeListing
from pipelex.mthds_parsing.helpers import is_pipelex_file
from pipelex.pipeline.exceptions import MethodEntryError
from pipelex.pipeline.method_entry import (
    MethodEntry,
    read_method_candidates,
    read_method_manifest,
    select_entry,
    select_named_pipe,
    tree_method_label,
)
from pipelex.pipeline.validate_bundle import dirs_beside_method
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error


class FolderReading(StrEnum):
    """What a command handed a method's folder reads of it."""

    # The pipe named, else the pipe the method starts at, in the bundle defining it: `run`, `inputs`, `build`.
    ENTRY_PIPE = "entry_pipe"
    # Every bundle of the method's tree, with no pipe to start at: `validate`, `fix`.
    WHOLE_TREE = "whole_tree"


class MethodFolderTarget(NamedTuple):
    """A method's folder handed to a command acting on one pipe: its tree, that pipe, and the bundle defining it."""

    tree: MethodTree
    #: The pipe named, as given, else the selected entry's `domain.pipe_code`.
    pipe_code: str
    #: The pipe the protocol's rule selected, or None when the caller named the pipe.
    entry: MethodEntry | None
    #: The file on this host of the bundle defining the selected entry, or None when the caller named the pipe.
    entry_bundle_file: Path | None


def list_method_folder(*, directory: Path, tree_listing: MethodTreeListing) -> MethodTree:
    """The method tree of a folder handed to a command, listed through the listing the command hands to its load.

    Raises:
        EmptyMethodTreeError: The tree holds no bundle: the membership rule keeps every file of the folder out of it, or
            none of the files it keeps is a bundle. The folder names no method, which each command reports as it reports
            a target it cannot resolve.
        ValidateBundleError: The tree is refused otherwise, or past this machine's limits, as the invalid verdict
            `validate` gives.
    """
    msg = f"The folder '{directory}' holds no .mthds bundle."
    try:
        tree = tree_listing.method_tree(handed_over=directory)
    except EmptyMethodTreeError as exc:
        raise EmptyMethodTreeError(msg) from exc
    except MethodTreeLoadError:
        with translate_to_validate_bundle_error():
            raise
    if not any(tree_path.endswith(BUNDLE_SUFFIX) for tree_path in tree.tree_paths):
        raise EmptyMethodTreeError(msg)
    return tree


def resolve_method_folder(*, directory: Path, pipe_override: str | None, tree_listing: MethodTreeListing) -> MethodFolderTarget:
    """List a method folder's tree, through the listing the command hands to its load, and settle the one pipe it acts on.

    Raises:
        MethodEntryError: The folder holds no bundle, or no pipe was named and the method has no single pipe to start
            at, or its manifest cannot be read: the target names no pipe, which each command reports as it reports a
            target it cannot resolve.
        ValidateBundleError: The tree is refused or past this machine's limits, or a bundle's declarations cannot be
            read, each as the invalid verdict `validate` gives.
    """
    try:
        tree = list_method_folder(directory=directory, tree_listing=tree_listing)
    except EmptyMethodTreeError as exc:
        msg = f"The folder '{directory}' holds no .mthds bundle, so it has no pipe to start at."
        raise MethodEntryError(msg).with_error_code(CoreCode.METHOD_INVALID) from exc
    if pipe_override:
        return MethodFolderTarget(tree=tree, pipe_code=pipe_override, entry=None, entry_bundle_file=None)
    with translate_to_validate_bundle_error():
        candidates = read_method_candidates(tree=tree)
    manifest = read_method_manifest(tree=tree)
    entry = select_entry(candidates=candidates, manifest=manifest, method_label=tree_method_label(tree=tree))
    return MethodFolderTarget(tree=tree, pipe_code=entry.pipe_ref, entry=entry, entry_bundle_file=tree.file_location(entry.tree_path))


def resolve_method_folder_run(*, directory: Path, pipe_override: str | None, tree_listing: MethodTreeListing) -> MethodFolderTarget:
    """A method folder as `run bundle` reads it: every refusal of the method is the verdict.

    The tree is listed through `tree_listing`, which the run hands to its load, so the run loads the tree listed here.

    Raises:
        ValidateBundleError: The tree is refused or past this machine's limits, or a bundle does not parse, each as the
            invalid verdict `validate` gives.
        MethodEntryError: The method has no single pipe to start at and `pipe_override` names none, which is no verdict
            on the method, coded as the refusal of a run that selects no pipe.
    """
    with translate_to_validate_bundle_error():
        return resolve_method_folder(directory=directory, pipe_override=pipe_override, tree_listing=tree_listing)


def locate_folder_pipe(*, tree: MethodTree, pipe_override: str | None) -> MethodEntry:
    """The bundle of a method's tree defining the pipe named, else the pipe the method starts at, and its bundle.

    For a command that judged the whole tree and then draws one pipe of it, such as `validate bundle --graph`.

    Raises:
        MethodEntryError: No pipe was named and the method has no single pipe to start at, or no single bundle of the
            method defines the pipe named.
        ValidateBundleError: A bundle's declarations cannot be read, as the invalid verdict `validate` gives.
    """
    with translate_to_validate_bundle_error():
        candidates = read_method_candidates(tree=tree)
    method_label = tree_method_label(tree=tree)
    if pipe_override:
        return select_named_pipe(candidates=candidates, pipe_ref=pipe_override, method_label=method_label)
    return select_entry(candidates=candidates, manifest=read_method_manifest(tree=tree), method_label=method_label)


def list_bundle_file_tree(*, bundle_file: Path, tree_listing: MethodTreeListing) -> MethodTree:
    """The method tree of a `.mthds` file named alone, as the run loads it.

    It is the member of the tree rooted at the nearest `METHODS.toml` at or above its folder, else the one-file tree of
    that file, from which a reference to any other file is refused. It is listed through `tree_listing`, which the run
    hands to its load, so the run places the file in the tree listed here.

    Raises:
        ValidateBundleError: The tree is refused or past this machine's limits, as the invalid verdict `validate` gives.
    """
    with translate_to_validate_bundle_error():
        return tree_listing.method_tree(handed_over=bundle_file)


class BundleTargetResolutionSuccess(NamedTuple):
    """A resolved bundle target: the bundle file or the method folder a command reads, the pipe it acts on, its library."""

    #: The file named, or the file of the bundle defining a folder's entry pipe; None for a folder read whole, or whose
    #: pipe was named.
    bundle_path: Path | None
    #: The pipe named, or a folder's entry pipe as `domain.pipe_code`; None for a file named with no pipe, which acts
    #: on its own `main_pipe`, and for a folder read whole with no pipe named.
    pipe_code: str | None
    #: The folder, then the `-L` directories, `~` expanded; None for a file named with no `-L`.
    library_dirs: list[Path] | None
    #: The folder named, `~` expanded, or None for a file.
    method_dir: Path | None
    #: The folder's method tree, or None for a file.
    method_tree: MethodTree | None
    #: The pipe the protocol's rule selected for a folder whose command acts on one pipe and named none, else None.
    entry: MethodEntry | None
    #: The listing the folder's tree was listed through, for the command to hand to its load; it holds nothing for a file.
    tree_listing: MethodTreeListing


class BundleTargetResolutionError(NamedTuple):
    """A path that is neither a `.mthds` file nor a directory: no bundle target, for the command to report."""

    input_path: str
    target_path: Path


def resolve_bundle_target_core(
    path: str,
    *,
    library_dir: list[str] | None,
    reading: FolderReading,
    pipe_override: str | None = None,
) -> BundleTargetResolutionSuccess | BundleTargetResolutionError:
    """Resolve a CLI path argument without deciding how errors are rendered.

    Args:
        path: The `path` argument, a `.mthds` file or a method's folder, `~` expanded.
        library_dir: The `-L/--library-dir` values as passed, `~` expanded.
        reading: What the command reads of a folder: the one pipe it acts on, or the whole tree.
        pipe_override: The pipe the caller named with `--pipe`, if any.

    Raises:
        EmptyMethodTreeError: For a folder read whole, it holds no bundle.
        MethodEntryError: For a folder whose command acts on one pipe, it holds no bundle, or no pipe was named and the
            method has no single pipe to start at.
        ValidateBundleError: For a folder, its tree is refused or a bundle's declarations cannot be read.
    """
    library_dirs = [Path(library_dir_item).expanduser() for library_dir_item in library_dir] if library_dir else None
    target_path = Path(path).expanduser()
    # The command's one listing: the folder's tree is listed through it here, and its load takes the tree from it.
    tree_listing = MethodTreeListing()

    if target_path.is_dir():
        # The folder first, then the -L directories that are not the folder, however either is spelled.
        library_dirs = [target_path, *dirs_beside_method(method_dir=target_path, library_dirs=library_dirs)]
        match reading:
            case FolderReading.ENTRY_PIPE:
                folder = resolve_method_folder(directory=target_path, pipe_override=pipe_override, tree_listing=tree_listing)
                return BundleTargetResolutionSuccess(
                    bundle_path=folder.entry_bundle_file,
                    pipe_code=folder.pipe_code,
                    library_dirs=library_dirs,
                    method_dir=target_path,
                    method_tree=folder.tree,
                    entry=folder.entry,
                    tree_listing=tree_listing,
                )
            case FolderReading.WHOLE_TREE:
                return BundleTargetResolutionSuccess(
                    bundle_path=None,
                    pipe_code=pipe_override,
                    library_dirs=library_dirs,
                    method_dir=target_path,
                    method_tree=list_method_folder(directory=target_path, tree_listing=tree_listing),
                    entry=None,
                    tree_listing=tree_listing,
                )

    if is_pipelex_file(target_path):
        return BundleTargetResolutionSuccess(
            bundle_path=target_path,
            pipe_code=pipe_override,
            library_dirs=library_dirs,
            method_dir=None,
            method_tree=None,
            entry=None,
            tree_listing=tree_listing,
        )

    return BundleTargetResolutionError(input_path=path, target_path=target_path)
