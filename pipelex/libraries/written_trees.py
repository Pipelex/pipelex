"""Method trees a host writes out to its own disk to load them, read back as written.

A server receives a method as a map of file entries, or reads a fetched package from its commit's git objects, and
writes the tree's files into a directory of its own to load them. Every file of that copy is a file of the tree, and
the membership rule is never applied to it again (`mthds/docs/spec/method-tree.md`, "A tree written out is read back as
written"): the map was the tree, and a second pass of the rule could drop a file the map holds, a file a `.gitignore`
of the tree names say.

While the writer holds a tree in `WRITTEN_METHOD_TREES`, every listing of its directory, as a library directory or as a
dependency package's root, returns the tree as written (`pipelex.libraries.method_trees`), and the loader names each
of its bundles by its tree path, never by the directory, which is a path on this host the caller never chose.
"""

import threading
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

from mthds.method_tree.exceptions import MethodTreeRefusedError, TreeSourceError
from mthds.method_tree.models import MethodTree
from mthds.method_tree.written_tree import read_written_tree

from pipelex.base_exceptions import PipelexUnexpectedError


class WrittenMethodTrees:
    """The method trees this process wrote out to load them, by the directory each was written as.

    Process-global like the local method file store: a request writes its tree, holds it here for the load, and releases
    it when the request ends, so a listing of the directory meanwhile returns the tree as written.
    """

    def __init__(self) -> None:
        self._trees: dict[Path, MethodTree] = {}
        self._lock = threading.Lock()

    def tree_written_at(self, *, directory: Path) -> MethodTree | None:
        """The tree held as written at `directory`, or None when no tree written there is held."""
        with self._lock:
            if not self._trees:
                return None
        resolved = directory.resolve()
        with self._lock:
            return self._trees.get(resolved)

    def holds_tree(self, *, tree: MethodTree) -> bool:
        """Whether `tree` is a tree held as written, so its files are named by their tree paths."""
        if tree.directory is None:
            return False
        return self.tree_written_at(directory=tree.directory) is tree

    @contextmanager
    def holding(self, *, tree: MethodTree) -> Generator[MethodTree, None, None]:
        """Hold a tree written out for as long as the block runs, and release it on the way out.

        Raises:
            PipelexUnexpectedError: The tree was not read from a directory, or another tree written at its directory is held.
        """
        if tree.directory is None:
            msg = "A method tree is held as written only when it was read back from the directory it was written as."
            raise PipelexUnexpectedError(msg)
        resolved = tree.directory.resolve()
        with self._lock:
            if resolved in self._trees:
                msg = f"A method tree written at '{resolved}' is already held."
                raise PipelexUnexpectedError(msg)
            self._trees[resolved] = tree
        try:
            yield tree
        finally:
            with self._lock:
                self._trees.pop(resolved, None)


WRITTEN_METHOD_TREES = WrittenMethodTrees()


def write_method_tree(*, contents: Mapping[str, bytes], destination: Path, expected_digest: str) -> MethodTree:
    """Write a tree's files at their tree paths as `destination`, and read the copy back as written.

    `destination` must not exist, or be an empty directory. The copy is read back as written (`read_written_tree`), and
    its digest must be the tree's: the files were checked as a tree before they were written, so a copy that reads back
    otherwise is this host's fault, never the caller's.

    Args:
        contents: Each file's bytes by its tree path, as a map of file entries carried them.
        destination: The directory to write the tree as.
        expected_digest: The digest of the tree the contents make.

    Returns:
        The tree as written, listed from `destination` resolved.

    Raises:
        PipelexUnexpectedError: The copy reads back as another tree, or as no tree at all.
        OSError: A file could not be written.
    """
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        msg = f"Cannot write a method tree at '{destination}': it already holds files."
        raise PipelexUnexpectedError(msg)
    for tree_path, data in contents.items():
        target = destination.joinpath(*tree_path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    try:
        written = read_written_tree(destination.resolve())
    except (MethodTreeRefusedError, TreeSourceError) as exc:
        msg = f"The method tree written at '{destination}' cannot be read back: {exc.message}"
        raise PipelexUnexpectedError(msg) from exc
    if written.digest != expected_digest:
        msg = f"The method tree written at '{destination}' reads back as {written.digest}, not as the tree it was written from, {expected_digest}."
        raise PipelexUnexpectedError(msg)
    return written
