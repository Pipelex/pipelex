"""The files a sandbox-hosted `PipeFunc` call receives, captured onto the library crate without importing anything.

A sandbox-hosted deployment never imports a method's Python in its own process: every call to a `PipeFunc` runs in a
sandbox that receives the files of the step's Python root, every file except the `.mthds` files, at their paths
(`wip/extra-files/design.md`, "Inside a run"). The crate carries them, per root, wherever the run travels, a Temporal
workflow included, which may read no file itself (`LibraryCrate.pipe_func_files`).

The generated `structures` module is the one file left behind: the sandbox generates its own from the crate's concepts,
with the qualified class names the runtime checks a return type against, and a method's own copy beside it would give
the sandbox two modules of that name.
"""

from mthds.method_tree.models import MethodTree

from pipelex.core.method_trees.tree_files import TreeFileEntry, read_call_files
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.methods.structures_check import is_generated_structures_module

_PYTHON_SUFFIX = ".py"
_PIPE_FUNC_TYPE = "PipeFunc"


def travels_with_call(*, tree_path: str, data: bytes) -> bool:
    """Whether a file of a `PipeFunc`'s Python root travels with its calls: every file but a generated `structures` module."""
    if not tree_path.endswith(_PYTHON_SUFFIX):
        return True
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return not is_generated_structures_module(source=source)


def with_tree_pipe_func_files(*, crate: LibraryCrate) -> LibraryCrate:
    """The crate, carrying the files of every method tree holding one of its `PipeFunc` steps, read from this host's disk.

    A tree whose files the crate already carries is not read again.
    """
    tree_keys = {
        tree_bundle_ref.tree_key
        for pipe_ref, tree_bundle_ref in crate.tree_bundles.items()
        if (blueprint := crate.pipes.get(pipe_ref)) is not None and blueprint.type == _PIPE_FUNC_TYPE
    }
    missing_keys = sorted(tree_keys - set(crate.pipe_func_files))
    if not missing_keys:
        return crate
    pipe_func_files: dict[str, dict[str, TreeFileEntry]] = dict(crate.pipe_func_files)
    for tree_key in missing_keys:
        tree = MethodTree.model_validate_json(crate.method_trees[tree_key])
        pipe_func_files[tree_key] = read_call_files(tree=tree, keeps=travels_with_call)
    return crate.model_copy(update={"pipe_func_files": pipe_func_files})
