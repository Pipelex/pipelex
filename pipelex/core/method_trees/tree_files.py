"""A method tree's files as they travel with a `PipeFunc` call: at their tree paths, in the standard's file entry forms.

A call to a `PipeFunc` that runs out of this process receives every file of its tree except the `.mthds` files, so the
function imports its sibling modules and reads a file beside its module as it does locally (`wip/extra-files/design.md`,
"Inside a run"). Each file travels as a file entry of `mthds/docs/spec/method-tree.md`, "The File Entry": its text
when its bytes are UTF-8, else `{"base64": "…"}`. A hash entry, which names bytes the receiver already holds, is
resolved by whoever holds the blobs before the files reach the process that writes them.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, TypeAlias

from mthds.method_tree.file_entry import Base64FileEntry
from mthds.method_tree.models import MethodTree
from mthds.method_tree.tree_path import tree_path_violation

from pipelex.core.method_trees.exceptions import TreePythonError

#: A file's bytes as they travel: its text when they are UTF-8, else in Base64.
TreeFileEntry: TypeAlias = str | Base64FileEntry

BUNDLE_SUFFIX = ".mthds"


class CallFileFilter(Protocol):
    """Decides, from a file's tree path and bytes, whether it travels with a call."""

    def __call__(self, *, tree_path: str, data: bytes) -> bool: ...


def encode_tree_file(*, data: bytes) -> TreeFileEntry:
    """The entry a file's bytes travel as: the text when they are UTF-8, else Base64."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return Base64FileEntry.make_from_bytes(data)


def tree_file_bytes(*, entry: TreeFileEntry) -> bytes:
    """The bytes a file entry carries."""
    if isinstance(entry, Base64FileEntry):
        return entry.data
    return entry.encode("utf-8")


def read_call_files(*, tree: MethodTree, keeps: CallFileFilter | None = None) -> dict[str, TreeFileEntry]:
    """Every file of a tree listed from this host's disk except its `.mthds` files, read as the entries a call receives.

    Args:
        tree: A tree listed from a directory of this host.
        keeps: Decides, from a file's tree path and bytes, whether it travels; every file travels when None.

    Returns:
        The files by tree path, in tree path order.
    """
    files: dict[str, TreeFileEntry] = {}
    for tree_path in tree.tree_paths:
        if tree_path.endswith(BUNDLE_SUFFIX):
            continue
        data = tree.file_location(tree_path).read_bytes()
        if keeps is not None and not keeps(tree_path=tree_path, data=data):
            continue
        files[tree_path] = encode_tree_file(data=data)
    return files


def write_call_files(*, files: Mapping[str, TreeFileEntry], destination: Path) -> None:
    """Write the files a call received into `destination`, each at its tree path.

    Raises:
        TreePythonError: A key is not a tree path, so it could name a place outside `destination`.
    """
    for tree_path, entry in files.items():
        violation = tree_path_violation(tree_path)
        if violation is not None:
            msg = f"The PipeFunc call received a file at '{tree_path}', which is not a tree path: {violation}."
            raise TreePythonError(msg)
        target = destination.joinpath(*tree_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(tree_file_bytes(entry=entry))
