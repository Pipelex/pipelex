"""A method tree's files as a `PipeFunc` call receives them: every file but the bundles, written at their tree paths.

A call to a `PipeFunc` that runs out of the process that loaded its method receives every file of its tree except the
`.mthds` files, so the function imports its sibling modules and reads a file beside its module as it does locally
(`wip/extra-files/design.md`, "Inside a run"). The call names its tree by digest; the process running it reads the files
through the method file store and writes them out here, or a sandbox client hands them to the sandbox it runs the call
in, which writes them the same way.
"""

from collections.abc import Mapping
from pathlib import Path

from mthds.method_tree.tree_path import tree_path_violation

from pipelex.core.method_trees.exceptions import TreePythonError

BUNDLE_SUFFIX = ".mthds"


def is_bundle_file(*, tree_path: str) -> bool:
    """Whether the file at `tree_path` is a bundle, which a `PipeFunc` call never receives."""
    return tree_path.endswith(BUNDLE_SUFFIX)


def write_call_files(*, files: Mapping[str, bytes], destination: Path) -> None:
    """Write the files a call received into `destination`, each at its tree path.

    Every key is checked before any file is written.

    Raises:
        TreePythonError: A key is not a tree path, so it could name a place outside `destination`.
    """
    for tree_path in files:
        violation = tree_path_violation(tree_path)
        if violation is not None:
            msg = f"The PipeFunc call received a file at '{tree_path}', which is not a tree path: {violation}."
            raise TreePythonError(msg)
    for tree_path, data in files.items():
        target = destination.joinpath(*tree_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
