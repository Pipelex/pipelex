"""The runner's blob store over a storage provider: what it looks up by size, what it reads, and how many at once.

The storage here counts its calls and the ones in flight, so these pin what the routes cannot show: a blob held at
another size than an entry states is never read, reads and lookups run a bounded number at a time, every write is
create-only with its checksum, a short object is never written over, and a tree whose listing is held is recorded
without a lookup per file.
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
from pytest_mock import MockerFixture
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
        self.created: list[tuple[str, str | None]] = []
        self.create_attempts: list[str] = []
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
        self.create_attempts.append(key)
        # Yield, so every create the store started at once is in flight together.
        await asyncio.sleep(0)
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

    async def test_bytes_that_do_not_hash_to_their_key_are_a_damaged_stored_file_never_retried(self, caplog: pytest.LogCaptureFixture) -> None:
        """A damaged object does not heal: a retry reads the same bytes, so the verdict is not to retry.

        No caller's doing, and no upload of theirs would change it: storage holds the object, but not the bytes the runtime
        stored, `pipelex.storage.damaged`, which the caller reports. Not `pipelex.storage.unavailable`, whose retry verdict would
        send a client round its retry budget, nor `runtime.misconfigured`, which tells the operator to change a setting
        none of which is wrong; the operator finds which object to remove in a record of its own, naming the hash.
        """
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        data = b"the true bytes"
        storage.objects[_blob_key(data)] = b"the damaged!!!"

        with caplog.at_level(logging.ERROR), pytest.raises(BlobStoreDamagedError) as exc_info:
            await read_request_tree(document=_hash_map({"file.txt": (data, len(data))}), blob_store=blob_store, label="The map", field="files")

        problem = problem_of(exc_info.value)
        assert problem["status"] == 500
        assert problem["code"] == "pipelex.storage.damaged"
        assert problem["retry"] == "no"
        assert problem["next_step"]["kind"] == "report"
        assert problem["params"] == {"scheme": "memory"}
        (record,) = [record for record in caplog.records if record.getMessage() == BLOB_DAMAGED_MESSAGE]
        assert record.levelno == logging.ERROR
        assert carried_attributes(record=record) == {
            "blob_sha256": sha256_hex(data),
            "blob_size_bytes": len(data),
            "read_size_bytes": len(b"the damaged!!!"),
            "storage_scheme": "memory",
        }

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

    async def test_a_short_object_is_asked_for_and_its_upload_is_a_server_fault_that_writes_nothing(self) -> None:
        """A blob cut short is damaged storage, which no write repairs: nothing writes over a blob, so its operator must."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        data = b"the whole blob, of which a failed write kept only a part"
        storage.objects[_blob_key(data)] = data[:10]

        assert await blob_store.missing_blobs(sizes={sha256_hex(data): len(data)}) == [sha256_hex(data)]
        with pytest.raises(BlobStoreDamagedError) as exc_info:
            await blob_store.store_blob(data=data)

        problem = problem_of(exc_info.value)
        assert problem["status"] == 500
        assert problem["code"] == "pipelex.storage.damaged"
        assert problem["params"] == {"scheme": "memory"}
        assert storage.objects[_blob_key(data)] == data[:10]
        assert storage.created == []
        assert storage.unconditional_keys == []

    async def test_blobs_and_listings_are_created_only_with_their_checksums(self) -> None:
        """Every write names its SHA-256, the blob's hash or the listing's digest, and none is unconditional."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        contents = {"main.mthds": b"domain = 'a'", "notes.txt": b"some notes"}
        request_tree = RequestTree.make_from_contents(contents=contents)

        await blob_store.record_tree(tree=request_tree.tree, contents=request_tree.contents)
        await blob_store.store_blob(data=contents["notes.txt"])

        digest_hex = digest_of_contents(contents).removeprefix("sha256:")
        assert sorted(storage.created) == sorted(
            [(_blob_key(data), sha256_hex(data)) for data in contents.values()] + [(f"{_SCOPE}/trees/{digest_hex}", digest_hex)]
        )
        assert storage.unconditional_keys == []

    async def test_files_of_the_same_bytes_are_one_blob_written_once(self) -> None:
        """Two empty `__init__.py` files name one blob key, which a tree records with one lookup and one create."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        contents = {"main.mthds": b"domain = 'a'", "pkg/__init__.py": b"", "pkg/sub/__init__.py": b""}
        request_tree = RequestTree.make_from_contents(contents=contents)

        await blob_store.record_tree(tree=request_tree.tree, contents=request_tree.contents)

        empty_key = _blob_key(b"")
        assert storage.sized_keys.count(empty_key) == 1
        assert storage.create_attempts.count(empty_key) == 1
        assert storage.objects[empty_key] == b""
        digest_hex = digest_of_contents(contents).removeprefix("sha256:")
        assert sorted(storage.created) == sorted(
            [(_blob_key(b"domain = 'a'"), sha256_hex(b"domain = 'a'")), (empty_key, sha256_hex(b"")), (f"{_SCOPE}/trees/{digest_hex}", digest_hex)]
        )

    async def test_a_blob_another_writer_created_meanwhile_is_held(self, mocker: MockerFixture) -> None:
        """The lookup found nothing, then the create found the key taken: the same bytes are held, and that is no error."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
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
