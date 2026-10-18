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

Every object under `blobs/<sha256>` holds, whole, the bytes whose SHA-256 is that hash: the key is the hash this runner
computes from the bytes it writes, the runner's own `PUT /v1/blobs/{sha256}` writes only bytes it checked against the
path's hash, and every built-in storage provider publishes a write whole or not at all (the local one through a
temporary file renamed onto the key). So an object's stored size, read from its metadata without reading its bytes, is
the size of that hash's bytes, and nothing deletes or rewrites a blob. A listing, written once each of its files was
held at its size, therefore stays true.

From this the blob store answers without reading what it does not need:

- `POST /v1/blobs/missing` lists a hash this runner does not hold at the size the sender states, an object held at
  another size included, which only a storage that does not publish writes whole could leave short, and which the
  upload then writes over.
- A run looks up each hash's stored size first. A hash held at another size than an entry states is a 422
  `request.invalid`, never `request.blobs_missing`, since uploading those bytes again would change nothing: the entry
  is wrong.
  Only a blob held at the size its entries state is read, so the bytes read are bounded by the sizes the request
  states, which its census already held to the tree's limits, and each is checked against its hash once read. Bytes
  that do not hash to their key mean the object stored under it is damaged, which no caller can repair and no retry
  cures: a 500 `pipelex.storage.not_found` naming the kind of storage, whose verdict is not to retry, and an error
  record, "Stored blob bytes do not match their hash", naming the hash for the operator to remove the object, after
  which the blob is uploaded again.

Lookups and reads run a bounded number at a time, so one request naming many blobs never opens them all at once.
"""

from collections.abc import Iterable, Mapping
from functools import partial

from mthds.method_tree.digest import DIGEST_PREFIX, sha256_hex, tree_listing
from mthds.method_tree.file_entry import BlobStore, InMemoryBlobStore
from mthds.method_tree.models import MethodTree
from pipelex import log
from pipelex.config import get_config
from pipelex.core.method_trees.exceptions import MethodFileUnavailableError
from pipelex.core.method_trees.method_files import TreeListing
from pipelex.runtime_hub import get_storage_provider
from pipelex.tools.misc.async_utils import gather_bounded
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.storage_config import StorageMethod
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract

from pipelex_api.exceptions import BlobStoreDamagedError

BLOBS_PREFIX = "blobs"
TREES_PREFIX = "trees"
_BLOB_CONTENT_TYPE = "application/octet-stream"
_LISTING_CONTENT_TYPE = "text/plain; charset=utf-8"
# How many lookups of a blob's size, which read metadata alone, and how many reads or writes of a blob's bytes, one
# request runs at a time.
MAX_CONCURRENT_BLOB_LOOKUPS = 16
MAX_CONCURRENT_BLOB_TRANSFERS = 4
# The message of the error record a blob read whose bytes do not match their hash writes, for the operator to search.
BLOB_DAMAGED_MESSAGE = "Stored blob bytes do not match their hash"


# The kind of storage a `pipelex.storage.*` problem names for a storage plugin's own backend.
PLUGIN_STORAGE_SCHEME = "plugin"


def problem_scheme_of(*, storage_method: str) -> str:
    """The kind of storage a `pipelex.storage.*` problem names for a configured storage method, as the registry spells it.

    `plugin` for a storage plugin's own method, whose kind the registry cannot list.
    """
    match storage_method:
        case StorageMethod.LOCAL:
            return "local"
        case StorageMethod.IN_MEMORY:
            return "memory"
        case StorageMethod.S3:
            return "s3"
        case StorageMethod.GCP:
            return "gcs"
        case _:
            # An external storage plugin's method token: the configured method is an open string.
            return PLUGIN_STORAGE_SCHEME


class RunnerBlobStore:
    """The blobs and tree listings of one caller's scope, over the deployment's storage provider."""

    def __init__(self, *, scope: str, storage: StorageProviderAbstract, scheme: str) -> None:
        """Build the blob store of one scope.

        Args:
            scope: The prefix of the scope's blobs and listings.
            storage: The storage provider holding them.
            scheme: The kind of storage the provider is, as a `pipelex.storage.*` problem names it (`problem_scheme_of`).
        """
        self._scope = scope
        self._storage = storage
        self._scheme = scheme

    @classmethod
    def make_for_scope(cls, *, scope: str) -> "RunnerBlobStore":
        """The blob store of `scope`, over the storage provider the runtime booted with."""
        scheme = problem_scheme_of(storage_method=get_config().runtime.storage.method)
        return cls(scope=scope, storage=get_storage_provider(), scheme=scheme)

    @property
    def scope(self) -> str:
        return self._scope

    def _blob_key(self, *, sha256: str) -> str:
        return f"{self._scope}/{BLOBS_PREFIX}/{sha256}"

    def _tree_key(self, *, tree_digest: str) -> str:
        return f"{self._scope}/{TREES_PREFIX}/{tree_digest.removeprefix(DIGEST_PREFIX)}"

    async def _holds_key(self, *, key: str) -> bool:
        try:
            await self._storage.load_size(f"{PIPELEX_STORAGE_SCHEME}{key}")
        except StorageFileNotFoundError:
            return False
        return True

    async def stored_size(self, *, sha256: str) -> int | None:
        """The size of the object stored under the hash `sha256`, read from its metadata, or None when there is none."""
        try:
            return await self._storage.load_size(f"{PIPELEX_STORAGE_SCHEME}{self._blob_key(sha256=sha256)}")
        except StorageFileNotFoundError:
            return None

    async def holds_blob(self, *, sha256: str, size: int) -> bool:
        """Whether the bytes whose SHA-256 is `sha256` are held at `size`, an object of another size being no blob."""
        return await self.stored_size(sha256=sha256) == size

    async def stored_sizes(self, *, sha256s: Iterable[str]) -> dict[str, int | None]:
        """Each hash's stored size, None for a hash not held, looked up a bounded number at a time."""
        hashes = list(sha256s)
        sizes = await gather_bounded([partial(self.stored_size, sha256=sha256) for sha256 in hashes], max_concurrency=MAX_CONCURRENT_BLOB_LOOKUPS)
        return dict(zip(hashes, sizes, strict=True))

    async def _read_verified(self, *, sha256: str, size: int) -> bytes:
        """The stored bytes of `sha256`, held at `size`, checked against their hash.

        Raises (as a problem document): a 500 `pipelex.storage.not_found` naming the kind of storage, for bytes that
        are not `size` bytes hashing to `sha256`, after an error record naming the hash, the one place the operator
        reads which damaged object to remove.
        """
        data = await self._storage.load(f"{PIPELEX_STORAGE_SCHEME}{self._blob_key(sha256=sha256)}")
        if len(data) != size or sha256_hex(data) != sha256:
            log.error(
                BLOB_DAMAGED_MESSAGE,
                fields={"blob_sha256": sha256, "blob_size_bytes": size, "read_size_bytes": len(data), "storage_scheme": self._scheme},
            )
            msg = (
                f"The bytes this runner's blob store holds under {sha256} do not hash to it: the storage holds a damaged "
                "object, which its operator removes for the blob to be uploaded again."
            )
            raise BlobStoreDamagedError(msg, scheme=self._scheme)
        return data

    async def read_held(self, *, sizes: Mapping[str, int]) -> BlobStore:
        """Read these held blobs, each at its stored size, as the synchronous blob store a map of file entries is read with.

        Args:
            sizes: Each hash to read, with the size it is held at, which the caller bounded before asking.
        """
        blobs = await gather_bounded(
            [partial(self._read_verified, sha256=sha256, size=size) for sha256, size in sizes.items()],
            max_concurrency=MAX_CONCURRENT_BLOB_TRANSFERS,
        )
        return InMemoryBlobStore(blobs)

    async def store_blob(self, *, data: bytes) -> str:
        """Hold `data` under its SHA-256, writing it unless it is held at its size already, and return the hash.

        An object under the hash at another size, which only a storage that does not publish writes whole could leave,
        is written over.
        """
        sha256 = sha256_hex(data)
        if not await self.holds_blob(sha256=sha256, size=len(data)):
            await self._storage.store(data, key=self._blob_key(sha256=sha256), content_type=_BLOB_CONTENT_TYPE)
        return sha256

    async def holds_tree(self, *, tree_digest: str) -> bool:
        """Whether the listing of the tree `tree_digest` names is held, which means every file of the tree is."""
        return await self._holds_key(key=self._tree_key(tree_digest=tree_digest))

    async def tree_hashes(self, *, tree_digest: str) -> set[str] | None:
        """The hashes of the files of the tree `tree_digest` names, when its listing is held, else None.

        The listing is read and checked against the digest, so a sender naming a tree it does not send learns nothing
        held that its own blobs are not part of.
        """
        try:
            listing = await self._storage.load(f"{PIPELEX_STORAGE_SCHEME}{self._tree_key(tree_digest=tree_digest)}")
        except StorageFileNotFoundError:
            return None
        try:
            tree_listing_read = TreeListing.parse(tree_digest=tree_digest, listing=listing)
        except MethodFileUnavailableError:
            # Not the listing the digest names: the tree is not held.
            return None
        return set(tree_listing_read.files.values())

    async def record_tree(self, *, tree: MethodTree, contents: Mapping[str, bytes]) -> None:
        """Hold every file of a tree read in full, then its listing, so a later request can send it by hash.

        The listing is written last, once every file it names is held, so a listing present always means its whole
        tree is, and a tree whose listing is held already is left as it is, without a lookup per file.

        Args:
            tree: The tree, as a map of file entries made it.
            contents: Each file's bytes by tree path.
        """
        if await self.holds_tree(tree_digest=tree.digest):
            return
        await gather_bounded([partial(self.store_blob, data=data) for data in contents.values()], max_concurrency=MAX_CONCURRENT_BLOB_TRANSFERS)
        await self._storage.store(tree_listing(tree.files), key=self._tree_key(tree_digest=tree.digest), content_type=_LISTING_CONTENT_TYPE)

    async def missing_blobs(self, *, sizes: Mapping[str, int]) -> list[str]:
        """The hashes of `sizes` not held at their size, in the mapping's order."""
        stored = await self.stored_sizes(sha256s=sizes)
        return [sha256 for sha256, size in sizes.items() if stored[sha256] != size]
