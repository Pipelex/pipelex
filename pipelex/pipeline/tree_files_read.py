"""The files of the method's tree each validated pipe reads (`tree_files_read`), and the per-file view of them (`tree_file_readers`).

A validation says, for each pipe it judged, which files of the method's tree the step reads, each by its tree path with
what it reads it as (`pipelex.core.method_trees.tree_file_reads`): a `PipeDocGen` step's template and the files its HTML
template names, a `PipeFunc` step's module. Each pipe resolved those names as it was built and validated, so this only
collects them. A client then shows which step uses each file, and an agent tells a file no step reads from one a step
needs (`wip/extra-files/design.md`, "Validation explains the method's files").

Both views are keyed the way every other validate artifact is: `tree_files_read` by namespaced `pipe_ref`, with the same
key set as `pipe_io_contracts`, a pipe that reads no file holding an empty list; `tree_file_readers` by tree path. The
pipes a validation judges are the ones of the method it was handed, which is one tree, so a tree path names one file.
"""

from collections.abc import Iterable, Mapping
from typing import Any, TypeAlias

from pipelex.core.method_trees.tree_file_reads import TreeFileRead
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract

#: The files of its method tree each pipe reads, keyed by namespaced `pipe_ref`.
TreeFilesRead: TypeAlias = dict[str, list[TreeFileRead]]


def build_tree_files_read(*, pipes: Iterable[PipeAbstract]) -> TreeFilesRead:
    """The files of its method tree each pipe reads, keyed by namespaced `pipe_ref`, in the pipes' order.

    Args:
        pipes: The validated pipes, the same ones `pipe_io_contracts` describes.

    Returns:
        One entry per pipe, an empty list for a pipe that reads no file of its tree.
    """
    return {pipe.pipe_ref: pipe.tree_files_read() for pipe in pipes}


def build_tree_file_readers(*, tree_files_read: Mapping[str, Iterable[TreeFileRead]]) -> dict[str, list[str]]:
    """The per-file view of `tree_files_read`: each tree path a pipe reads, to the refs of the pipes that read it.

    Args:
        tree_files_read: The files each pipe reads, keyed by namespaced `pipe_ref`.

    Returns:
        The tree paths in sorted order, each with its readers in the order `tree_files_read` lists them, each once.
    """
    readers: dict[str, list[str]] = {}
    for pipe_ref, files_read in tree_files_read.items():
        for file_read in files_read:
            pipe_refs = readers.setdefault(file_read.tree_path, [])
            if pipe_ref not in pipe_refs:
                pipe_refs.append(pipe_ref)
    return {tree_path: readers[tree_path] for tree_path in sorted(readers)}


def tree_files_envelope_fields(*, pipes: Iterable[PipeAbstract]) -> dict[str, Any]:
    """The two views as the JSON-ready members of an agent-CLI validate envelope, `tree_files_read` and `tree_file_readers`.

    Args:
        pipes: The validated pipes.

    Returns:
        The envelope's two members, in the canonical report's shapes.
    """
    tree_files_read = build_tree_files_read(pipes=pipes)
    return {
        "tree_files_read": {
            pipe_ref: [file_read.model_dump(mode="json") for file_read in files_read] for pipe_ref, files_read in tree_files_read.items()
        },
        "tree_file_readers": build_tree_file_readers(tree_files_read=tree_files_read),
    }
