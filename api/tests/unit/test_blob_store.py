"""The runner's blob store over a storage provider: what it looks up by size, what it reads, and how many at once.

The storage here counts its calls and the ones in flight, so these pin what the routes cannot show: a blob held at
another size than an entry states is never read, reads and lookups run a bounded number at a time, every write is
create-only with its checksum, a short object is never written over, and a tree whose listing is held is recorded
without a lookup per file.
"""

import asyncio
import json

import pytest
from mthds.method_tree.digest import digest_of_contents, sha256_hex, tree_files_from_contents, tree_listing
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract, StoredData
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex_api.blob_store import MAX_CONCURRENT_BLOB_LOOKUPS, MAX_CONCURRENT_BLOB_TRANSFERS, RunnerBlobStore
from pipelex_api.errors import ApiError
from pipelex_api.method_tree_request import RequestTree, read_request_tree

_SCOPE = "single-tenant"


class _CountingStorage(StorageProviderAbstract):
    """An in-memory storage counting its reads and size lookups, and the most of each it served at once."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.loaded_keys: list[str] = []
        self.sized_keys: list[str] = []
        self.created: list[tuple[str, str | None]] = []
        self.unconditional_keys: list[str] = []
        self.most_loads_at_once = 0
        self.most_lookups_at_once = 0
        self._loads_in_flight = 0
        self._lookups_in_flight = 0

    @override
    async def _load_with_metadata(self, key: str) -> StoredData:
        self._loads_in_flight += 1
        self.most_loads_at_once = max(self.most_loads_at_once, self._loads_in_flight)
        try:
            # Yield, so every read the store started at once is in flight together.
            await asyncio.sleep(0)
            self.loaded_keys.append(key)
            if key not in self.objects:
                msg = f"File not found: '{key}'"
                raise StorageFileNotFoundError(msg)
            return StoredData(data=self.objects[key], mime_type=None)
        finally:
            self._loads_in_flight -= 1

    @override
    async def _load_size(self, key: str) -> int:
        self._lookups_in_flight += 1
        self.most_lookups_at_once = max(self.most_lookups_at_once, self._lookups_in_flight)
        try:
            await asyncio.sleep(0)
            self.sized_keys.append(key)
            if key not in self.objects:
                msg = f"File not found: '{key}'"
                raise StorageFileNotFoundError(msg)
            return len(self.objects[key])
        finally:
            self._lookups_in_flight -= 1

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None) -> None:
        self.unconditional_keys.append(key)
        self.objects[key] = data

    @override
    async def _store_if_absent(self, *, data: bytes, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> bool:
        if key in self.objects:
            return False
        self.created.append((key, checksum_sha256_hex))
        self.objects[key] = data
        return True

    @override
    async def public_url(self, uri: str) -> str | None:
        return None


def _blob_key(data: bytes) -> str:
    return f"{_SCOPE}/blobs/{sha256_hex(data)}"


def _hash_map(entries: dict[str, tuple[bytes, int]]) -> str:
    """A map of file entries naming each file's bytes by hash, at the size given beside them."""
    return json.dumps({tree_path: {"sha256": sha256_hex(data), "size": size} for tree_path, (data, size) in entries.items()})


def _problem_of(exc_info: pytest.ExceptionInfo[ApiError]) -> dict[str, object]:
    document: dict[str, object] = exc_info.value.document
    return document


@pytest.mark.asyncio(loop_scope="class")
class TestRunnerBlobStore:
    async def test_a_blob_held_at_another_size_is_refused_before_any_byte_is_read(self) -> None:
        """An entry stating a size other than the held bytes' is a `BlobMismatch`, and the census bounds every read."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage)
        large = b"x" * 4096
        await blob_store.store_blob(data=large)

        with pytest.raises(ApiError) as exc_info:
            await read_request_tree(document=_hash_map({"large.bin": (large, 0)}), blob_store=blob_store, label="The `files` map")

        problem = _problem_of(exc_info)
        assert exc_info.value.status_code == 422
        assert problem["error_type"] == "BlobMismatch"
        assert problem["mismatched_blobs"] == [{"sha256": sha256_hex(large), "held_size": len(large)}]
        assert storage.loaded_keys == []

    async def test_a_blob_not_held_is_missing_and_a_held_one_is_read_and_checked(self) -> None:
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage)
        held = b"held bytes"
        absent = b"absent bytes"
        await blob_store.store_blob(data=held)

        with pytest.raises(ApiError) as exc_info:
            await read_request_tree(
                document=_hash_map({"held.txt": (held, len(held)), "absent.txt": (absent, len(absent))}), blob_store=blob_store, label="The map"
            )
        assert _problem_of(exc_info)["missing_blobs"] == [sha256_hex(absent)]

        tree = await read_request_tree(document=_hash_map({"held.txt": (held, len(held))}), blob_store=blob_store, label="The map")
        assert tree == RequestTree.make_from_contents(contents={"held.txt": held})

    async def test_bytes_that_do_not_hash_to_their_key_are_a_server_fault(self) -> None:
        """Damaged storage is no caller's doing, and no upload of theirs would change it: a 500 naming the hash."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage)
        data = b"the true bytes"
        storage.objects[_blob_key(data)] = b"the damaged!!!"

        with pytest.raises(ApiError) as exc_info:
            await read_request_tree(document=_hash_map({"file.txt": (data, len(data))}), blob_store=blob_store, label="The map")

        assert exc_info.value.status_code == 500
        assert _problem_of(exc_info)["error_type"] == "BlobStoreCorrupted"

    async def test_lookups_and_reads_run_a_bounded_number_at_a_time(self) -> None:
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage)
        blobs = [f"file number {index_blob}".encode() for index_blob in range(3 * MAX_CONCURRENT_BLOB_LOOKUPS)]
        for data in blobs:
            storage.objects[_blob_key(data)] = data

        stored = await blob_store.stored_sizes(sha256s=[sha256_hex(data) for data in blobs])
        held = await blob_store.read_held(sizes={sha256: size for sha256, size in stored.items() if size is not None})

        assert [held.read_blob(sha256_hex(data)) for data in blobs] == blobs
        assert storage.most_lookups_at_once == MAX_CONCURRENT_BLOB_LOOKUPS
        assert storage.most_loads_at_once == MAX_CONCURRENT_BLOB_TRANSFERS

    async def test_a_short_object_is_asked_for_and_its_upload_is_a_server_fault_that_writes_nothing(self) -> None:
        """A blob cut short is damaged storage, which no write repairs: nothing writes over a blob, so its operator must."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage)
        data = b"the whole blob, of which a failed write kept only a part"
        storage.objects[_blob_key(data)] = data[:10]

        assert await blob_store.missing_blobs(sizes={sha256_hex(data): len(data)}) == [sha256_hex(data)]
        with pytest.raises(ApiError) as exc_info:
            await blob_store.store_blob(data=data)

        assert exc_info.value.status_code == 500
        assert _problem_of(exc_info)["error_type"] == "BlobStoreCorrupted"
        assert storage.objects[_blob_key(data)] == data[:10]
        assert storage.created == []
        assert storage.unconditional_keys == []

    async def test_blobs_and_listings_are_created_only_with_their_checksums(self) -> None:
        """Every write names its SHA-256, the blob's hash or the listing's digest, and none is unconditional."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage)
        contents = {"main.mthds": b"domain = 'a'", "notes.txt": b"some notes"}
        request_tree = RequestTree.make_from_contents(contents=contents)

        await blob_store.record_tree(tree=request_tree.tree, contents=request_tree.contents)
        await blob_store.store_blob(data=contents["notes.txt"])

        digest_hex = digest_of_contents(contents).removeprefix("sha256:")
        assert sorted(storage.created) == sorted(
            [(_blob_key(data), sha256_hex(data)) for data in contents.values()] + [(f"{_SCOPE}/trees/{digest_hex}", digest_hex)]
        )
        assert storage.unconditional_keys == []

    async def test_a_blob_another_writer_created_meanwhile_is_held(self, mocker: MockerFixture) -> None:
        """The lookup found nothing, then the create found the key taken: the same bytes are held, and that is no error."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage)
        data = b"bytes two writers send at once"

        async def _absent_then_created(key: str) -> int:
            # The lookup misses, and the other writer's object lands before this writer's create.
            storage.objects[key] = data
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg)

        mocker.patch.object(storage, "_load_size", side_effect=_absent_then_created)

        assert await blob_store.store_blob(data=data) == sha256_hex(data)
        assert storage.created == []
        assert storage.objects[_blob_key(data)] == data

    async def test_a_tree_whose_listing_is_held_is_recorded_without_a_lookup_per_file(self) -> None:
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage)
        contents = {f"file_{index_file}.txt": f"content {index_file}".encode() for index_file in range(5)}
        request_tree = RequestTree.make_from_contents(contents=contents)
        await blob_store.record_tree(tree=request_tree.tree, contents=request_tree.contents)
        lookups_after_first = len(storage.sized_keys)

        await blob_store.record_tree(tree=request_tree.tree, contents=request_tree.contents)

        assert len(storage.sized_keys) == lookups_after_first + 1
        assert await blob_store.tree_hashes(tree_digest=digest_of_contents(contents)) == {sha256_hex(data) for data in contents.values()}

    async def test_a_listing_that_is_not_the_digest_s_holds_no_tree(self) -> None:
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage)
        contents = {"a.txt": b"a"}
        digest = digest_of_contents(contents)
        other_listing = tree_listing(tree_files_from_contents({"b.txt": b"b"}))
        storage.objects[f"{_SCOPE}/trees/{digest.removeprefix('sha256:')}"] = other_listing

        assert await blob_store.tree_hashes(tree_digest=digest) is None
