"""The files an out-of-process `PipeFunc` call receives: its method tree's, read through the method file store.

A call to a `PipeFunc` that runs out of the process that loaded its method, in a sandbox or in an activity, receives the
files of the step's tree, every file except the `.mthds` files, at their tree paths (`wip/extra-files/design.md`, "Inside
a run"). The call names the tree by digest (`PipeFuncExecutionRequest.tree_digest`), and whoever runs it reads the files
through the method file store under the run's read scope, where IO is allowed, never in a workflow.

The generated `structures` module is the one file left behind: the process running the call generates its own from the
crate's concepts, with the qualified class names the runtime checks a return type against, and a method's own copy
beside it would give it two modules of that name.
"""

from pipelex.core.method_trees.method_files import read_tree_files
from pipelex.core.method_trees.tree_files import is_bundle_file
from pipelex.methods.structures_check import is_generated_structures_module

_PYTHON_SUFFIX = ".py"


def travels_with_call(*, tree_path: str, data: bytes) -> bool:
    """Whether a file of a `PipeFunc`'s tree travels with its calls: every file but a generated `structures` module."""
    if not tree_path.endswith(_PYTHON_SUFFIX):
        return True
    try:
        source = data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return not is_generated_structures_module(source=source)


async def read_pipe_func_call_files(*, tree_digest: str, read_scope: str | None) -> dict[str, bytes]:
    """The files a call of a `PipeFunc` of the tree `tree_digest` names receives, by tree path, read through the method file store.

    Raises:
        MethodFileUnavailableError: The store does not hold the tree or one of its files for this run.
    """
    files = await read_tree_files(tree_digest=tree_digest, read_scope=read_scope, keeps=lambda tree_path: not is_bundle_file(tree_path=tree_path))
    return {tree_path: data for tree_path, data in files.items() if travels_with_call(tree_path=tree_path, data=data)}
