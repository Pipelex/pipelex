"""The method file store: where the process that uses a method file reads it, by the digest of its tree and its hash.

A run's library crate names each tree it loads by its digest and carries none of its bytes (`wip/extra-files/design.md`,
"Inside a run"). Whatever later needs a file of the method, a `PipeFunc` call writing its tree for the function to import,
a `PipeDocGen` print reading its template, reads it through this one seam, where IO is allowed: in the activity that
uses the file, never in a workflow. The store answers two questions, laid out as the hosted plane lays out its blobs: the
listing of a tree, by the tree's digest, and a file's bytes, by their SHA-256. `pipelex.core.method_trees.method_files`
does the rest: it checks the listing against the digest and each file against the hash the listing names.

Every read carries the run's read scope, the trusted prefix the host scopes the run's reads to: a hosted implementation
builds its keys from it, so a run reads the method files of its own organization only. The local implementation below
serves one process and ignores it.

`LocalMethodFileStore` is pipelex's own implementation and the default one: it serves the trees this process's
libraries listed or were handed, while those libraries hold them. A tree listed from a directory is read from the disk,
and checked against the hash its listing recorded, so a file edited after the listing is not served as the file the run
validated; a tree a library assembled in memory, such as the files submitted with bundles loaded from content strings,
is served from the bytes it holds. A host whose activities run in another process than the one that listed the tree,
such as a Temporal worker, claims `HubSlot.METHOD_FILE_STORE` with an implementation reading its own blob store.
"""

import asyncio
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import NamedTuple, Protocol

from mthds.method_tree.digest import sha256_hex, tree_digest, tree_listing
from mthds.method_tree.models import MethodTree, TreeFile
from mthds.method_tree.tree_path import sorted_tree_paths
from typing_extensions import override


class MethodFileStoreProtocol(Protocol):
    """Reads a tree's listing by the tree's digest, and a file's bytes by their SHA-256, under the run's read scope."""

    async def read_tree_listing(self, *, tree_digest: str, read_scope: str | None) -> bytes | None:
        """The listing of the tree whose digest is `tree_digest`, as the standard writes it, or None when not held.

        Args:
            tree_digest: The tree's digest, `sha256:` and 64 lowercase hexadecimal digits.
            read_scope: The run's read scope, which a hosted store builds its keys from; None for an unscoped run.
        """
        ...

    async def read_blob(self, *, sha256: str, read_scope: str | None) -> bytes | None:
        """The bytes whose SHA-256 is `sha256`, in lowercase hexadecimal, or None when not held.

        Args:
            sha256: The SHA-256 of the bytes, as a tree's listing names it.
            read_scope: The run's read scope, which a hosted store builds its keys from; None for an unscoped run.
        """
        ...


class HeldFile(NamedTuple):
    """A file of a tree the local store holds: its hash and size, and where its bytes are, on disk or in memory."""

    sha256: str
    size: int
    source: Path | bytes

    @classmethod
    def of_bytes(cls, *, data: bytes) -> "HeldFile":
        return cls(sha256=sha256_hex(data), size=len(data), source=data)


class _HeldTree(NamedTuple):
    tree: MethodTree
    files: dict[str, HeldFile]


class _HeldFileKey(NamedTuple):
    """Which holder holds a file, in which tree and at which tree path: the key of the store's index by hash."""

    holder: str
    tree_digest: str
    tree_path: str


def tree_of_held_files(*, files: Mapping[str, HeldFile]) -> MethodTree:
    """The tree whose files are `files`, keyed by tree path, read from no directory: its listing and its digest.

    The caller has checked that every key is a tree path and that no two collide.
    """
    tree_files = [TreeFile(path=tree_path, sha256=files[tree_path].sha256, size=files[tree_path].size) for tree_path in sorted_tree_paths(files)]
    return MethodTree(files=tree_files, digest=tree_digest(tree_files))


class LocalMethodFileStore(MethodFileStoreProtocol):
    """The trees this process's libraries hold, served from the disk they were listed from or from the bytes held for them.

    A library holds the trees it loads, under its own id, until it is torn down (`release`), so a tree is served while
    any run of a library holding it may still read it. Two libraries holding the same tree serve it from either's
    sources, since a digest names the same files wherever they are read from: a file is served from the first source
    whose bytes still match its hash.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # holder -> tree digest -> the tree as that holder listed or assembled it, with where its files are read from.
        self._held: dict[str, dict[str, _HeldTree]] = {}
        # sha256 -> every held file with those bytes, in the order they were held: the index `read_blob` reads, so a read
        # of every file of a tree costs one lookup per file rather than a scan of every held file.
        self._by_sha256: dict[str, dict[_HeldFileKey, HeldFile]] = {}

    def hold_tree(self, *, holder: str, tree: MethodTree) -> None:
        """Serve `tree`, listed from a directory of this host, for `holder` until it releases its trees.

        Raises:
            ValueError: The tree was not listed from a directory, so this store cannot read its files.
        """
        if tree.directory is None:
            msg = "A tree held from the disk is a tree listed from a directory; one assembled in memory is held with hold_files."
            raise ValueError(msg)
        files = {
            tree_file.path: HeldFile(sha256=tree_file.sha256, size=tree_file.size, source=tree.file_location(tree_file.path))
            for tree_file in tree.files
        }
        self._hold(holder=holder, held_tree=_HeldTree(tree=tree, files=files))

    def hold_files(self, *, holder: str, files: Mapping[str, HeldFile]) -> MethodTree:
        """Serve the tree whose files are `files`, keyed by tree path, for `holder` until it releases its trees, and return it.

        The caller has checked that every key is a tree path and that no two collide.
        """
        tree = tree_of_held_files(files=files)
        self._hold(holder=holder, held_tree=_HeldTree(tree=tree, files=dict(files)))
        return tree

    def _hold(self, *, holder: str, held_tree: _HeldTree) -> None:
        tree_digest = held_tree.tree.digest
        with self._lock:
            held_trees = self._held.setdefault(holder, {})
            # A holder holding a tree it already holds keeps its first sources.
            if tree_digest in held_trees:
                return
            held_trees[tree_digest] = held_tree
            for tree_path, held_file in held_tree.files.items():
                key = _HeldFileKey(holder=holder, tree_digest=tree_digest, tree_path=tree_path)
                self._by_sha256.setdefault(held_file.sha256, {})[key] = held_file

    def holds(self, *, holder: str, tree_digest: str) -> bool:
        """Whether `holder` already holds the tree `tree_digest`."""
        with self._lock:
            return tree_digest in self._held.get(holder, {})

    def _held_trees(self, *, tree_digest: str) -> list[_HeldTree]:
        """Every holder's record of the tree `tree_digest`, in the order the holders first held a tree."""
        with self._lock:
            return [held_trees[tree_digest] for held_trees in self._held.values() if tree_digest in held_trees]

    def release(self, *, holder: str) -> None:
        """Stop serving the trees `holder` held, except from the sources another holder still holds them with."""
        with self._lock:
            held_trees = self._held.pop(holder, {})
            for tree_digest, held_tree in held_trees.items():
                for tree_path, held_file in held_tree.files.items():
                    same_bytes = self._by_sha256.get(held_file.sha256)
                    if same_bytes is None:
                        continue
                    same_bytes.pop(_HeldFileKey(holder=holder, tree_digest=tree_digest, tree_path=tree_path), None)
                    if not same_bytes:
                        del self._by_sha256[held_file.sha256]

    def release_all(self) -> None:
        """Stop serving every tree."""
        with self._lock:
            self._held = {}
            self._by_sha256 = {}

    def held_files_with_hash(self, *, sha256: str) -> list[HeldFile]:
        """Every held file whose bytes have the SHA-256 `sha256`, in the order they were held, wherever their bytes are."""
        with self._lock:
            return list(self._by_sha256.get(sha256, {}).values())

    def held_tree(self, *, tree_digest: str) -> MethodTree | None:
        """The tree held under `tree_digest`, as listed or assembled, or None when no library holds it."""
        held_trees = self._held_trees(tree_digest=tree_digest)
        return held_trees[0].tree if held_trees else None

    def read_held_file(self, *, tree_digest: str, tree_path: str) -> bytes | None:
        """The bytes of the file at `tree_path` of the tree held under `tree_digest`, checked against its hash, or None.

        None when the tree is not held, holds no file at `tree_path`, or holds one on disk whose bytes changed since the
        tree was listed or that can no longer be read.
        """
        for held_tree in self._held_trees(tree_digest=tree_digest):
            held_file = held_tree.files.get(tree_path)
            if held_file is None:
                return None
            data = _read_held_file(held_file=held_file)
            if data is not None:
                return data
        return None

    @override
    async def read_tree_listing(self, *, tree_digest: str, read_scope: str | None) -> bytes | None:
        # One process, one organization: the read scope selects nothing here.
        held_tree = self.held_tree(tree_digest=tree_digest)
        if held_tree is None:
            return None
        return tree_listing(held_tree.files)

    @override
    async def read_blob(self, *, sha256: str, read_scope: str | None) -> bytes | None:
        # One process, one organization: the read scope selects nothing here.
        for held_file in self.held_files_with_hash(sha256=sha256):
            match held_file.source:
                case bytes() as data:
                    return data
                case Path():
                    # Reading and hashing a file on disk blocks, so it runs off the event loop.
                    read_from_disk = await asyncio.to_thread(_read_held_file, held_file=held_file)
                    if read_from_disk is not None:
                        return read_from_disk
        return None


def _read_held_file(*, held_file: HeldFile) -> bytes | None:
    """The bytes of a held file when they still match its hash, or None."""
    match held_file.source:
        case bytes() as data:
            return data
        case Path() as location:
            try:
                data = location.read_bytes()
            except OSError:
                return None
            if sha256_hex(data) != held_file.sha256:
                return None
            return data


#: The store this process's libraries hold their trees in, and the default the runtime hub reads method files through.
LOCAL_METHOD_FILES = LocalMethodFileStore()
