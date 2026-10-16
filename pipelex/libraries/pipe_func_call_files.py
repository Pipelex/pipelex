"""The files a sandbox-hosted `PipeFunc` call receives, captured onto the library crate without importing anything.

A sandbox-hosted deployment never imports a method's Python in its own process: every call to a `PipeFunc` runs in a
sandbox that receives the files of the step's Python root, every file except the `.mthds` files, at their paths
(`wip/extra-files/design.md`, "Inside a run"). They are read once, as the library loads, for each method tree holding a
`PipeFunc` step, and the crate carries them, per root, wherever the run travels, a Temporal workflow included, which may
read no file itself (`LibraryCrate.pipe_func_files`); a directory the load read them from may be gone by then, such as
the temporary one a server writes a request's files into.

The generated `structures` module is the one file left behind: the sandbox generates its own from the crate's concepts,
with the qualified class names the runtime checks a return type against, and a method's own copy beside it would give
the sandbox two modules of that name.
"""

from mthds.method_tree.models import MethodTree

from pipelex.core.method_trees.tree_files import TreeFileEntry, read_call_files
from pipelex.methods.structures_check import is_generated_structures_module
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint

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


def holds_pipe_func_step(*, blueprint: PipelexBundleBlueprint) -> bool:
    """Whether a bundle declares a `PipeFunc` step, whose calls carry its tree's files."""
    return any(pipe_blueprint.type == _PIPE_FUNC_TYPE for pipe_blueprint in (blueprint.pipe or {}).values())


def tree_pipe_func_files(*, tree: MethodTree) -> dict[str, TreeFileEntry]:
    """The files every `PipeFunc` call of a method tree listed from this host's disk receives, read from the disk now."""
    return read_call_files(tree=tree, keeps=travels_with_call)
