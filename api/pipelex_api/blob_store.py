"""The runner's blob store: bytes keyed by their SHA-256, and the listings of the trees it holds in full.

A sender asks which of its hashes the runner lacks (`POST /v1/blobs/missing`), uploads only those
(`PUT /v1/blobs/{sha256}`), then sends its method as a map of file entries naming them by hash. This runner keeps those
bytes in its configured storage provider, local or cloud, so a self-hosted deployment gets the shape the hosted plane
has (`wip/extra-files/design.md`, D5 and D6), under one prefix per caller:

    <scope>/blobs/<sha256>   a file's bytes, written once and never changed
    <scope>/trees/<hex>      a tree's listing, under the hexadecimal part of its digest

The scope is the run's trusted read scope, the one a multi-tenant host sends for the organization it serves, or else the
caller's own id (`single-tenant` on a deployment that identifies no caller): a hash entry resolves only in the caller's
own scope, never across tenants, so asking whether a hash is held tells a caller nothing of another's files.

A listing is written only after every file it names is held, by this runner once it has read a request's tree in
full, and never by an upload: `PUT /v1/blobs/{sha256}` writes under `blobs/` alone, so an uploaded file that happens to
be a well-formed listing proves nothing. A listing present means the whole tree is present, which lets
`POST /v1/blobs/missing` answer a tree's digest with one lookup.

Whether a blob is held is read as whether its key exists: a blob is written only once its bytes were checked against
its hash, so it has one size, and the size a sender states is checked when the blob is read for a run, never on a
lookup.
"""

import asyncio
from collections.abc import Mapping

from mthds.method_tree.digest import DIGEST_PREFIX, sha256_hex, tree_listing
from mthds.method_tree.file_entry import BlobStore, InMemoryBlobStore
from mthds.method_tree.models import MethodTree
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract

BLOBS_PREFIX = "blobs"
TREES_PREFIX = "trees"
_BLOB_CONTENT_TYPE = "application/octet-stream"
_LISTING_CONTENT_TYPE = "text/plain; charset=utf-8"


class RunnerBlobStore:
    """The blobs and tree listings of one caller's scope, over the deployment's storage provider."""

    def __init__(self, *, scope: str, storage: StorageProviderAbstract) -> None:
        self._scope = scope
        self._storage = storage

    @classmethod
    def make_for_scope(cls, *, scope: str) -> "RunnerBlobStore":
        """The blob store of `scope`, over the storage provider the runtime booted with."""
        return cls(scope=scope, storage=get_storage_provider())

    @property
    def scope(self) -> str:
        return self._scope

    def _blob_key(self, *, sha256: str) -> str:
        return f"{self._scope}/{BLOBS_PREFIX}/{sha256}"

    def _tree_key(self, *, tree_digest: str) -> str:
        return f"{self._scope}/{TREES_PREFIX}/{tree_digest.removeprefix(DIGEST_PREFIX)}"

    async def _holds_key(self, *, key: str) -> bool:
        try:
            await self._storage.load_head(f"{PIPELEX_STORAGE_SCHEME}{key}", nb_bytes=1)
        except StorageFileNotFoundError:
            return False
        return True

    async def holds_blob(self, *, sha256: str) -> bool:
        """Whether the bytes whose SHA-256 is `sha256` are held."""
        return await self._holds_key(key=self._blob_key(sha256=sha256))

    async def read_blob(self, *, sha256: str) -> bytes | None:
        """The bytes whose SHA-256 is `sha256`, or None when they are not held."""
        try:
            return await self._storage.load(f"{PIPELEX_STORAGE_SCHEME}{self._blob_key(sha256=sha256)}")
        except StorageFileNotFoundError:
            return None

    async def store_blob(self, *, data: bytes) -> str:
        """Hold `data` under its SHA-256, writing it only when it is not held yet, and return the hash."""
        sha256 = sha256_hex(data)
        if not await self.holds_blob(sha256=sha256):
            await self._storage.store(data, key=self._blob_key(sha256=sha256), content_type=_BLOB_CONTENT_TYPE)
        return sha256

    async def holds_tree(self, *, tree_digest: str) -> bool:
        """Whether the listing of the tree `tree_digest` names is held, which means every file of the tree is."""
        return await self._holds_key(key=self._tree_key(tree_digest=tree_digest))

    async def record_tree(self, *, tree: MethodTree, contents: Mapping[str, bytes]) -> None:
        """Hold every file of a tree read in full, then its listing, so a later request can send it by hash.

        The listing is written last, once every file it names is held, so a listing present always means its whole
        tree is.

        Args:
            tree: The tree, as a map of file entries made it.
            contents: Each file's bytes by tree path.
        """
        await asyncio.gather(*(self.store_blob(data=data) for data in contents.values()))
        if not await self.holds_tree(tree_digest=tree.digest):
            await self._storage.store(tree_listing(tree.files), key=self._tree_key(tree_digest=tree.digest), content_type=_LISTING_CONTENT_TYPE)

    async def prefetched(self, *, sha256s: set[str]) -> BlobStore:
        """The held bytes of these hashes, read at once, as the synchronous blob store a map of file entries is read with."""
        hashes = sorted(sha256s)
        blobs = await asyncio.gather(*(self.read_blob(sha256=sha256) for sha256 in hashes))
        return InMemoryBlobStore([blob for blob in blobs if blob is not None])
