"""What `run bundle` runs when it is handed a method's folder or a bundle file: its method tree, and where it starts.

Both CLIs read their target here, so `pipelex run bundle` and `pipelex-agent run bundle` run the same pipe of the same
tree for the same arguments, locally as on the hosted API:

- A folder is the method rooted at the nearest `METHODS.toml` at or above it, else at the folder itself. With no
  `--pipe`, the run starts where the MTHDS protocol says a run naming no pipe starts (`pipelex.pipeline.method_entry`):
  the manifest's `main_pipe`, else the one `main_pipe` its bundles declare; none or several is refused, the bundles
  named by their tree paths.
- A `.mthds` file named alone is the member of its own file's tree: rooted at the nearest `METHODS.toml` at or above
  its folder, else the one-file tree of that file, from which a reference to any other file is refused. It starts at
  its own `main_pipe`, as it always has.

The tree is listed under this machine's limits (`[interpreter.method_tree_limits]`), and its digest is what a run
records as the method it ran.
"""

from pathlib import Path
from typing import NamedTuple

from mthds.method_tree.models import MethodTree

from pipelex.libraries.method_trees import list_local_method_tree
from pipelex.pipeline.method_entry import MethodEntry, select_method_entry
from pipelex.pipeline.validate_bundle_translation import translate_to_validate_bundle_error


class MethodFolderRun(NamedTuple):
    """A method's folder to run: its tree, the pipe the run starts at, and the bundle defining it when it was selected."""

    tree: MethodTree
    #: `--pipe` as given, else the selected entry's `domain.pipe_code`.
    pipe_code: str
    #: The pipe the protocol's rule selected, or None when `--pipe` named one.
    entry: MethodEntry | None
    #: The file on this host of the bundle defining the selected entry, or None when `--pipe` named the pipe.
    entry_bundle_file: Path | None


def resolve_method_folder_run(*, directory: Path, pipe_override: str | None) -> MethodFolderRun:
    """List a method folder's tree and settle the pipe its run starts at.

    Raises:
        ValidateBundleError: The tree is refused or past this machine's limits, a bundle does not parse, or the method
            has no single pipe to start at, each as the invalid verdict `validate` gives.
    """
    with translate_to_validate_bundle_error():
        tree = list_local_method_tree(handed_over=directory)
        if pipe_override:
            return MethodFolderRun(tree=tree, pipe_code=pipe_override, entry=None, entry_bundle_file=None)
        entry = select_method_entry(tree=tree)
    return MethodFolderRun(tree=tree, pipe_code=entry.pipe_ref, entry=entry, entry_bundle_file=tree.file_location(entry.tree_path))


def list_bundle_file_tree(*, bundle_file: Path) -> MethodTree:
    """The method tree of a `.mthds` file named alone, as the run loads it.

    Raises:
        ValidateBundleError: The tree is refused or past this machine's limits, as the invalid verdict `validate` gives.
    """
    with translate_to_validate_bundle_error():
        return list_local_method_tree(handed_over=bundle_file)
