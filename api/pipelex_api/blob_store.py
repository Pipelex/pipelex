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

Every write is create-only and checksummed, as the hosted platform writes the same keys: a blob or a listing is created
only when its key holds nothing (`If-None-Match: *` on S3, generation 0 on GCS, a hard link on the local filesystem),
so nothing written there is ever replaced, and with its SHA-256 as its checksum, which S3 checks against the body it
receives. A key already holding an object is the object already held, never an error. The checksum of a blob is its
hash, and that of a listing the hexadecimal part of its tree's digest, which is the listing's own hash, so every object
under `blobs/<hex>` or `trees/<hex>` holds bytes whose SHA-256 is that `<hex>`, and a bucket refusing every
unconditional write under those prefixes refuses none of this runner's.

Every object under `blobs/<sha256>` holds, whole, the bytes whose SHA-256 is that hash: the key is the hash this runner
computes from the bytes it writes, the runner's own `PUT /v1/blobs/{sha256}` writes only bytes it checked against the
path's hash, and every built-in storage provider publishes a write whole or not at all. So an object's stored size,
read from its metadata without reading its bytes, is the size of that hash's bytes, and nothing deletes or rewrites a
blob. A listing, written once each of its files was held at its size, therefore stays true.

From this the blob store answers without reading what it does not need:

- `POST /v1/blobs/missing` lists a hash this runner does not hold at the size the sender states, an object held at
  another size included. The upload then tells the two cases apart, holding the bytes: bytes of the size held are the
  ones held, and nothing is written, while bytes of another size mean the object held is damaged, which only a storage
  that does not publish writes whole could leave, a 500 `pipelex.storage.damaged`, since nothing writes over a blob
  and its operator must remove the object.
- A run reads each hash's bytes in one request, a read of at most one byte more than the largest size its entries
  state, so the bytes read are bounded by the sizes the request states, which its census already held to the tree's
  limits, whatever size the object is held at. A hash held at another size than an entry states, which the length read
  shows, is a 422 `request.invalid`, never `request.blobs_missing`, since uploading those bytes again would change
  nothing: the entry is wrong. Only that refusal looks the size held up, for the operator's message, when the read
  stopped short of the object's end.
  Bytes read at the size their entries state are checked against their hash. Bytes that do not hash to their key mean
  the object stored under it is damaged, which no caller can repair and no retry cures: a 500
  `pipelex.storage.damaged` naming the kind of storage, whose verdict is not to retry, and an error record, "Stored blob
  bytes do not match their hash", naming the hash for the operator to remove the object, after which the blob is
  uploaded again.

Lookups and reads run a bounded number at a time, so one request naming many blobs never opens them all at once.
"""

from collections.abc import Iterable, Mapping
from functools import partial
from typing import NamedTuple

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
# How many lookups of a blob's size, which read metadata alone, how many reads of the blobs a request names, each
# bounded by the size the request states for it, and how many writes of a blob's bytes one request runs at a time. The
# S3 provider's pool of connections holds at least as many as the first two (`S3_MAX_POOL_CONNECTIONS`).
MAX_CONCURRENT_BLOB_LOOKUPS = 16
MAX_CONCURRENT_BLOB_READS = 16
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


class StatedBlobs(NamedTuple):
    """The blobs a map of file entries names by hash, as the blob store holds them."""

    held: BlobStore
    """The bytes of each hash held at the size its entries state, checked against the hash."""

    mismatched: dict[str, int]
    """Each hash held at another size than an entry states, with the size it is held at, in hash order."""


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

    async def stored_sizes(self, *, sha256s: Iterable[str]) -> dict[str, int | None]:
        """Each hash's stored size, None for a hash not held, looked up a bounded number at a time."""
        hashes = list(sha256s)
        sizes = await gather_bounded([partial(self.stored_size, sha256=sha256) for sha256 in hashes], max_concurrency=MAX_CONCURRENT_BLOB_LOOKUPS)
        return dict(zip(hashes, sizes, strict=True))

    async def _read_bounded(self, *, sha256: str, nb_bytes: int) -> bytes | None:
        """At most `nb_bytes` leading bytes of the blob `sha256`, read in one request, or None when the hash is not held."""
        try:
            return await self._storage.load_head(f"{PIPELEX_STORAGE_SCHEME}{self._blob_key(sha256=sha256)}", nb_bytes=nb_bytes)
        except StorageFileNotFoundError:
            return None

    async def read_stated(self, *, stated_sizes: Mapping[str, set[int]]) -> StatedBlobs:
        """Read the blobs a map of file entries names, each in one request bounded by the sizes its entries state.

        Each hash is read for at most one byte more than the largest size its entries state, so a hash held at a larger
        size shows it without its bytes being read, and the bytes read stay bounded by the sizes stated. A hash not
        held is left out, for the reader to report among the blobs this runner does not hold.

        Args:
            stated_sizes: Each hash the map names, with every size its entries state for it, which the map's census
                held to the tree's limits.

        Raises (as a problem document): a 500 `pipelex.storage.damaged` naming the kind of storage, when no hash is
        held at another size and bytes read at the size their entries state do not hash to their key, after an error
        record naming each such hash, the one place the operator reads which damaged object to remove.
        """
        hashes = sorted(stated_sizes)
        reads = await gather_bounded(
            [partial(self._read_bounded, sha256=sha256, nb_bytes=max(stated_sizes[sha256]) + 1) for sha256 in hashes],
            max_concurrency=MAX_CONCURRENT_BLOB_READS,
        )
        blobs: dict[str, bytes] = {}
        mismatched: dict[str, int] = {}
        for sha256, data in zip(hashes, reads, strict=True):
            if data is None:
                continue
            sizes = stated_sizes[sha256]
            if sizes == {len(data)}:
                blobs[sha256] = data
            elif len(data) <= max(sizes):
                mismatched[sha256] = len(data)
            else:
                # The read stopped a byte past the largest size stated: the object is larger, and its size is looked up.
                held_size = await self.stored_size(sha256=sha256)
                if held_size is not None:
                    mismatched[sha256] = held_size
        if mismatched:
            return StatedBlobs(held=InMemoryBlobStore(), mismatched=mismatched)
        damaged = [sha256 for sha256, data in blobs.items() if sha256_hex(data) != sha256]
        for sha256 in damaged:
            log.error(
                BLOB_DAMAGED_MESSAGE,
                fields={
                    "blob_sha256": sha256,
                    "blob_size_bytes": len(blobs[sha256]),
                    "read_size_bytes": len(blobs[sha256]),
                    "storage_scheme": self._scheme,
                },
            )
        if damaged:
            msg = (
                f"The bytes this runner's blob store holds under {damaged[0]} do not hash to it: the storage holds a damaged "
                "object, which its operator removes for the blob to be uploaded again."
            )
            raise BlobStoreDamagedError(msg, scheme=self._scheme)
        return StatedBlobs(held=InMemoryBlobStore(list(blobs.values())), mismatched={})

    async def store_blob(self, *, data: bytes) -> str:
        """Hold `data` under its SHA-256, creating the blob unless it is held already, and return the hash.

        The blob is looked up first, so bytes already held are not sent again, then created only if its key is still
        free, with its hash as its checksum: a writer that created it meanwhile wrote the same bytes, and the key
        holding an object is the blob held.

        Raises (as a problem document): a 500 `pipelex.storage.damaged` naming the kind of storage when an object of
        another size is held under the hash, which only damaged storage could hold and which this runner never writes
        over, after the error record naming the hash that a read of damaged bytes writes.
        """
        sha256 = sha256_hex(data)
        await self._store_hashed_blob(sha256=sha256, data=data)
        return sha256

    async def _store_hashed_blob(self, *, sha256: str, data: bytes) -> None:
        """Hold `data`, whose SHA-256 is `sha256`, as `store_blob` does, for a caller that hashed it already."""
        held_size = await self.stored_size(sha256=sha256)
        if held_size is None:
            await self._storage.store_if_absent(
                data=data, key=self._blob_key(sha256=sha256), content_type=_BLOB_CONTENT_TYPE, checksum_sha256_hex=sha256
            )
        elif held_size != len(data):
            log.error(
                BLOB_DAMAGED_MESSAGE,
                fields={"blob_sha256": sha256, "blob_size_bytes": held_size, "read_size_bytes": len(data), "storage_scheme": self._scheme},
            )
            msg = (
                f"This runner's blob store holds {held_size} bytes under {sha256}, whose bytes are {len(data)} long: its "
                "storage is damaged, and its operator must remove that object for the blob to be uploaded again."
            )
            raise BlobStoreDamagedError(msg, scheme=self._scheme)

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
        tree is, and a tree whose listing is held already is left as it is, without a lookup per file. The listing is
        created only if its key is free, with the hexadecimal part of the tree's digest as its checksum, which is the
        listing's own hash: a listing held already, whoever wrote it, is the same bytes.

        Args:
            tree: The tree, as a map of file entries made it.
            contents: Each file's bytes by tree path. Files of the same bytes are held as one blob, written once.
        """
        if await self.holds_tree(tree_digest=tree.digest):
            return
        # One write per distinct blob: two files of the same bytes, such as two empty files, name one key, and two
        # concurrent creates of one key would race each other for nothing.
        blobs_by_hash = {sha256_hex(data): data for data in contents.values()}
        await gather_bounded(
            [partial(self._store_hashed_blob, sha256=sha256, data=data) for sha256, data in blobs_by_hash.items()],
            max_concurrency=MAX_CONCURRENT_BLOB_TRANSFERS,
        )
        await self._storage.store_if_absent(
            data=tree_listing(tree.files),
            key=self._tree_key(tree_digest=tree.digest),
            content_type=_LISTING_CONTENT_TYPE,
            checksum_sha256_hex=tree.digest.removeprefix(DIGEST_PREFIX),
        )

    async def missing_blobs(self, *, sizes: Mapping[str, int]) -> list[str]:
        """The hashes of `sizes` not held at their size, in the mapping's order."""
        stored = await self.stored_sizes(sha256s=sizes)
        return [sha256 for sha256, size in sizes.items() if stored[sha256] != size]
