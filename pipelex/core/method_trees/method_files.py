"""A method file named by its tree's digest and its tree path, and the reads that reach it through the method file store.

A library crate names each tree a run loads by its digest, and a step names a file of its tree by the file's tree path,
so a method file travels as a `MethodFileRef` and its bytes are read only where they are used, in an activity, through
the method file store the runtime hub holds (`pipelex.core.method_trees.method_file_store`). Every read is checked: the
listing against the digest that names it, and each file against the hash the listing names, so a store serving the
wrong bytes is refused rather than trusted.
"""

from collections.abc import Callable, Iterable

from mthds.method_tree.digest import DIGEST_PREFIX, is_sha256_hex, sha256_hex
from mthds.method_tree.tree_path import tree_path_violation
from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel, ConfigDict

from pipelex.core.method_trees.exceptions import MethodFileUnavailableError
from pipelex.core.method_trees.tree_bundle import MethodFileRef
from pipelex.runtime_hub import get_method_file_store

#: The separator between a file's hash and its tree path on a line of a tree's listing.
_LISTING_SEPARATOR = "  "
#: What ends each line of a tree's listing, and the only character that does.
_LISTING_LINE_END = "\n"


class TreeListing(BaseModel):
    """A tree's listing, read and checked against its digest: each file's SHA-256, by tree path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree_digest: str
    files: dict[str, str]

    @classmethod
    def parse(cls, *, tree_digest: str, listing: bytes) -> "TreeListing":
        """Read a tree's listing, as the standard writes it, after checking that it is the listing `tree_digest` names.

        Raises:
            MethodFileUnavailableError: The bytes are not the listing the digest names, or not a listing at all.
        """
        if DIGEST_PREFIX + sha256_hex(listing) != tree_digest:
            msg = f"The listing the method file store returned for the tree '{tree_digest}' is not the one its digest names."
            raise MethodFileUnavailableError(msg)
        try:
            text = listing.decode("utf-8")
        except UnicodeDecodeError as exc:
            msg = f"The listing of the tree '{tree_digest}' is not UTF-8 text."
            raise MethodFileUnavailableError(msg) from exc
        # The standard ends every line with a line feed, and only a line feed separates them: a tree path may hold any
        # other character `str.splitlines` would split on, such as U+2028 or U+2029.
        if text and not text.endswith(_LISTING_LINE_END):
            msg = f"The listing of the tree '{tree_digest}' does not end with a line feed."
            raise MethodFileUnavailableError(msg)
        files: dict[str, str] = {}
        for line in text.split(_LISTING_LINE_END)[:-1]:
            sha256, separator, tree_path = line.partition(_LISTING_SEPARATOR)
            if not separator or not is_sha256_hex(sha256) or tree_path_violation(tree_path) is not None:
                msg = f"The listing of the tree '{tree_digest}' holds a line that is not a file's hash and tree path."
                raise MethodFileUnavailableError(msg)
            files[tree_path] = sha256
        return cls(tree_digest=tree_digest, files=files)


async def read_tree_listing(*, tree_digest: str, read_scope: str | None) -> TreeListing:
    """The listing of the tree `tree_digest` names, read through the method file store under the run's read scope.

    Raises:
        MethodFileUnavailableError: The store does not hold the tree, or serves a listing its digest does not name.
    """
    listing = await get_method_file_store().read_tree_listing(tree_digest=tree_digest, read_scope=read_scope)
    if listing is None:
        msg = f"The method file store holds no tree '{tree_digest}' for this run."
        raise MethodFileUnavailableError(msg)
    return TreeListing.parse(tree_digest=tree_digest, listing=listing)


async def read_listed_file(*, listing: TreeListing, tree_path: str, read_scope: str | None) -> bytes:
    """The bytes of the file at `tree_path` in a tree whose listing was read, through the method file store and checked.

    Raises:
        MethodFileUnavailableError: The listing names no file at `tree_path`, the store does not hold its bytes, or it
            serves bytes the listing does not name.
    """
    sha256 = listing.files.get(tree_path)
    if sha256 is None:
        msg = f"The tree '{listing.tree_digest}' holds no file '{tree_path}'."
        raise MethodFileUnavailableError(msg).with_error_code(CoreCode.METHOD_RESOURCE_MISSING)
    data = await get_method_file_store().read_blob(sha256=sha256, read_scope=read_scope)
    if data is None:
        msg = f"The method file store does not hold the file '{tree_path}' of the tree '{listing.tree_digest}' for this run."
        raise MethodFileUnavailableError(msg)
    if sha256_hex(data) != sha256:
        msg = f"The bytes the method file store returned for the file '{tree_path}' of the tree '{listing.tree_digest}' are not the file's."
        raise MethodFileUnavailableError(msg)
    return data


async def read_method_file(*, file_ref: MethodFileRef, read_scope: str | None) -> bytes:
    """The bytes of a method file, read through the method file store under the run's read scope and checked against its hash.

    Raises:
        MethodFileUnavailableError: The store does not hold the tree or the file, or serves bytes the tree does not name.
    """
    listing = await read_tree_listing(tree_digest=file_ref.tree_digest, read_scope=read_scope)
    return await read_listed_file(listing=listing, tree_path=file_ref.tree_path, read_scope=read_scope)


async def read_tree_files(*, tree_digest: str, read_scope: str | None, keeps: Callable[[str], bool] | None = None) -> dict[str, bytes]:
    """The files of the tree `tree_digest` names, by tree path, read through the method file store and checked.

    Args:
        tree_digest: The tree's digest.
        read_scope: The run's read scope.
        keeps: Decides, from a file's tree path, whether it is read; every file is read when None.

    Raises:
        MethodFileUnavailableError: The store does not hold the tree or one of its files, or serves bytes the tree does not name.
    """
    listing = await read_tree_listing(tree_digest=tree_digest, read_scope=read_scope)
    files: dict[str, bytes] = {}
    for tree_path in listing.files:
        if keeps is not None and not keeps(tree_path):
            continue
        files[tree_path] = await read_listed_file(listing=listing, tree_path=tree_path, read_scope=read_scope)
    return files


class StoredTree(BaseModel):
    """A method tree as a store keeps it: its listing, under the tree's digest, and its files' bytes, under their hashes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree_digest: str
    listing: bytes
    blobs: dict[str, bytes]


async def read_stored_trees(*, tree_digests: Iterable[str], read_scope: str | None) -> list[StoredTree]:
    """Every tree `tree_digests` names, as a store keeps it, read through the method file store and checked.

    What an orchestrator that runs a job out of process copies into the store its workers read, for every tree the job's
    crate names (`LibraryCrate.tree_digests`), before its `execute` or `start` returns: the runner may drop the files a
    tree was listed from as soon as it does, such as the temporary directory it wrote a request's files into, and the
    library holding the tree in this process is torn down with the request (`OrchestratorProtocol`).

    Raises:
        MethodFileUnavailableError: The store does not hold a tree or one of its files, or serves bytes the tree does not name.
    """
    method_file_store = get_method_file_store()
    stored_trees: list[StoredTree] = []
    for tree_digest in tree_digests:
        listing_bytes = await method_file_store.read_tree_listing(tree_digest=tree_digest, read_scope=read_scope)
        if listing_bytes is None:
            msg = f"The method file store holds no tree '{tree_digest}' for this run."
            raise MethodFileUnavailableError(msg)
        listing = TreeListing.parse(tree_digest=tree_digest, listing=listing_bytes)
        blobs: dict[str, bytes] = {}
        for tree_path, sha256 in listing.files.items():
            if sha256 not in blobs:
                blobs[sha256] = await read_listed_file(listing=listing, tree_path=tree_path, read_scope=read_scope)
        stored_trees.append(StoredTree(tree_digest=tree_digest, listing=listing_bytes, blobs=blobs))
    return stored_trees
