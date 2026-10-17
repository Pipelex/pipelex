"""The runner's blob store over a storage provider: what it looks up by size, what it reads, and how many at once.

The storage here counts its calls and the ones in flight, so these pin what the routes cannot show: a blob held at
another size than an entry states is never read, reads and lookups run a bounded number at a time, a short object is
written over by the next upload, and a tree whose listing is held is recorded without a lookup per file.
"""

import asyncio
import json
import logging

import pytest
from mthds.method_tree.digest import digest_of_contents, sha256_hex, tree_files_from_contents, tree_listing
from pipelex.tools.log.log_fields import carried_attributes
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.storage_config import StorageMethod
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract, StoredData
from typing_extensions import override

from pipelex_api.blob_store import (
    BLOB_DAMAGED_MESSAGE,
    MAX_CONCURRENT_BLOB_LOOKUPS,
    MAX_CONCURRENT_BLOB_TRANSFERS,
    RunnerBlobStore,
    problem_scheme_of,
)
from pipelex_api.exceptions import BlobStoreDamagedError, RunnerRequestError
from pipelex_api.method_tree_request import RequestTree, read_request_tree
from tests.unit._problems import problem_of

_SCOPE = "single-tenant"


class _CountingStorage(StorageProviderAbstract):
    """An in-memory storage counting its reads and size lookups, and the most of each it served at once."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.loaded_keys: list[str] = []
        self.sized_keys: list[str] = []
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
        self.objects[key] = data

    @override
    async def public_url(self, uri: str) -> str | None:
        return None


def _blob_key(data: bytes) -> str:
    return f"{_SCOPE}/blobs/{sha256_hex(data)}"


def _hash_map(entries: dict[str, tuple[bytes, int]]) -> str:
    """A map of file entries naming each file's bytes by hash, at the size given beside them."""
    return json.dumps({tree_path: {"sha256": sha256_hex(data), "size": size} for tree_path, (data, size) in entries.items()})


@pytest.mark.asyncio(loop_scope="class")
class TestRunnerBlobStore:
    async def test_a_blob_held_at_another_size_is_refused_before_any_byte_is_read(self) -> None:
        """An entry stating a size other than the held bytes' is a `request.invalid`, and the census bounds every read."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        large = b"x" * 4096
        await blob_store.store_blob(data=large)

        with pytest.raises(RunnerRequestError) as exc_info:
            await read_request_tree(document=_hash_map({"large.bin": (large, 0)}), blob_store=blob_store, label="The `files` map", field="files")

        problem = problem_of(exc_info.value)
        assert problem["status"] == 422
        assert problem["code"] == "request.invalid"
        assert problem["params"] == {"field": "files"}
        # The hash and the size held ride the operator's message alone.
        assert f"{sha256_hex(large)}" in problem["diagnostics"]["message"]
        assert storage.loaded_keys == []

    async def test_a_blob_not_held_is_missing_and_a_held_one_is_read_and_checked(self) -> None:
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        held = b"held bytes"
        absent = b"absent bytes"
        await blob_store.store_blob(data=held)

        with pytest.raises(RunnerRequestError) as exc_info:
            await read_request_tree(
                document=_hash_map({"held.txt": (held, len(held)), "absent.txt": (absent, len(absent))}),
                blob_store=blob_store,
                label="The map",
                field="files",
            )
        problem = problem_of(exc_info.value)
        assert problem["code"] == "request.blobs_missing"
        assert problem["params"] == {"missing_blobs": [sha256_hex(absent)]}

        tree = await read_request_tree(document=_hash_map({"held.txt": (held, len(held))}), blob_store=blob_store, label="The map", field="files")
        assert tree == RequestTree.make_from_contents(contents={"held.txt": held})

    async def test_bytes_that_do_not_hash_to_their_key_are_unavailable_storage(self, caplog: pytest.LogCaptureFixture) -> None:
        """Damaged storage is no caller's doing, and no upload of theirs would change it: storage failed the read.

        Not `runtime.misconfigured`, which tells the operator to change a setting none of which is wrong; the operator
        finds which object to clear in a record of its own, naming the hash.
        """
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        data = b"the true bytes"
        storage.objects[_blob_key(data)] = b"the damaged!!!"

        with caplog.at_level(logging.ERROR), pytest.raises(BlobStoreDamagedError) as exc_info:
            await read_request_tree(document=_hash_map({"file.txt": (data, len(data))}), blob_store=blob_store, label="The map", field="files")

        problem = problem_of(exc_info.value)
        assert problem["status"] == 503
        assert problem["code"] == "pipelex.storage.unavailable"
        assert problem["params"] == {"scheme": "memory"}
        (record,) = [record for record in caplog.records if record.getMessage() == BLOB_DAMAGED_MESSAGE]
        assert record.levelno == logging.ERROR
        assert carried_attributes(record=record)["blob.sha256"] == sha256_hex(data)

    async def test_lookups_and_reads_run_a_bounded_number_at_a_time(self) -> None:
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        blobs = [f"file number {index_blob}".encode() for index_blob in range(3 * MAX_CONCURRENT_BLOB_LOOKUPS)]
        for data in blobs:
            storage.objects[_blob_key(data)] = data

        stored = await blob_store.stored_sizes(sha256s=[sha256_hex(data) for data in blobs])
        held = await blob_store.read_held(sizes={sha256: size for sha256, size in stored.items() if size is not None})

        assert [held.read_blob(sha256_hex(data)) for data in blobs] == blobs
        assert storage.most_lookups_at_once == MAX_CONCURRENT_BLOB_LOOKUPS
        assert storage.most_loads_at_once == MAX_CONCURRENT_BLOB_TRANSFERS

    async def test_a_short_object_is_not_held_and_the_next_upload_writes_it_over(self) -> None:
        """A storage that does not publish writes whole may leave a blob cut short: it is asked for again, then repaired."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        data = b"the whole blob, of which a failed write kept only a part"
        storage.objects[_blob_key(data)] = data[:10]

        assert await blob_store.missing_blobs(sizes={sha256_hex(data): len(data)}) == [sha256_hex(data)]
        await blob_store.store_blob(data=data)

        assert storage.objects[_blob_key(data)] == data
        assert await blob_store.missing_blobs(sizes={sha256_hex(data): len(data)}) == []

    async def test_a_tree_whose_listing_is_held_is_recorded_without_a_lookup_per_file(self) -> None:
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        contents = {f"file_{index_file}.txt": f"content {index_file}".encode() for index_file in range(5)}
        request_tree = RequestTree.make_from_contents(contents=contents)
        await blob_store.record_tree(tree=request_tree.tree, contents=request_tree.contents)
        lookups_after_first = len(storage.sized_keys)

        await blob_store.record_tree(tree=request_tree.tree, contents=request_tree.contents)

        assert len(storage.sized_keys) == lookups_after_first + 1
        assert await blob_store.tree_hashes(tree_digest=digest_of_contents(contents)) == {sha256_hex(data) for data in contents.values()}

    async def test_a_listing_that_is_not_the_digest_s_holds_no_tree(self) -> None:
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        contents = {"a.txt": b"a"}
        digest = digest_of_contents(contents)
        other_listing = tree_listing(tree_files_from_contents({"b.txt": b"b"}))
        storage.objects[f"{_SCOPE}/trees/{digest.removeprefix('sha256:')}"] = other_listing

        assert await blob_store.tree_hashes(tree_digest=digest) is None


class TestProblemScheme:
    @pytest.mark.parametrize(
        ("storage_method", "scheme"),
        [
            (StorageMethod.LOCAL, "local"),
            (StorageMethod.IN_MEMORY, "memory"),
            (StorageMethod.S3, "s3"),
            (StorageMethod.GCP, "gcs"),
            ("azure", None),
        ],
    )
    def test_the_problem_names_the_kind_of_storage_as_the_registry_spells_it(self, storage_method: str, scheme: str | None) -> None:
        assert problem_scheme_of(storage_method=storage_method) == scheme
        params = problem_of(BlobStoreDamagedError("damaged", scheme=scheme)).get("params")
        assert params == ({"scheme": scheme} if scheme is not None else None)
