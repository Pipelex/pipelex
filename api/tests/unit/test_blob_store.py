"""The runner's blob store over a storage provider: what it looks up by size, what it reads, and how many at once.

The storage here counts its calls and the ones in flight, so these pin what the routes cannot show: a request's blobs
are read in one request each, never past a byte more than the size stated, a blob held at another size than an entry
states is refused without its bytes read, reads and lookups run a bounded number at a time, every write is create-only
with its checksum, a short object is never written over, and a tree whose listing is held is recorded without a lookup
per file.
"""

import asyncio
import json
import logging
from typing import Any

import pytest
from mthds.method_tree.digest import digest_of_contents, sha256_hex, tree_files_from_contents, tree_listing
from pipelex.base_exceptions import PipelexError
from pipelex.tools.log.log_fields import carried_attributes
from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.s3_storage_provider import S3_MAX_POOL_CONNECTIONS
from pipelex.tools.storage.storage_config import StorageMethod
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract, StoredData
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex_api.blob_store import (
    BLOB_DAMAGED_MESSAGE,
    MAX_CONCURRENT_BLOB_LOOKUPS,
    MAX_CONCURRENT_BLOB_READS,
    RunnerBlobStore,
    problem_scheme_of,
)
from pipelex_api.exceptions import BlobStoreDamagedError, RequestMethodError, RunnerRequestError
from pipelex_api.method_tree_request import RequestTree, read_request_tree
from tests.unit._problems import problem_of

_SCOPE = "single-tenant"


class _CountingStorage(StorageProviderAbstract):
    """An in-memory storage counting its reads and size lookups, and the most of each it served at once."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.loaded_keys: list[str] = []
        self.head_reads: list[tuple[str, int]] = []
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
    async def _load_head(self, key: str, *, nb_bytes: int) -> bytes:
        self._loads_in_flight += 1
        self.most_loads_at_once = max(self.most_loads_at_once, self._loads_in_flight)
        try:
            await asyncio.sleep(0)
            self.head_reads.append((key, nb_bytes))
            if key not in self.objects:
                msg = f"File not found: '{key}'"
                raise StorageFileNotFoundError(msg)
            return self.objects[key][:nb_bytes]
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
    async def _store(self, data: bytes, *, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> None:
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


# A blob the store holds, and a hash entry naming it at another size than the one it is held at.
_LARGE_BLOB = b"x" * 4096
_HASH_HELD_AT_ANOTHER_SIZE = {"sha256": sha256_hex(_LARGE_BLOB), "size": 10}


def _hash_map(entries: dict[str, tuple[bytes, int]]) -> str:
    """A map of file entries naming each file's bytes by hash, at the size given beside them."""
    return json.dumps({tree_path: {"sha256": sha256_hex(data), "size": size} for tree_path, (data, size) in entries.items()})


@pytest.mark.asyncio(loop_scope="class")
class TestRunnerBlobStore:
    async def test_a_blob_held_larger_than_stated_is_refused_reading_one_byte_past_the_size_stated(self) -> None:
        """An entry stating a size other than the held bytes' is a `request.invalid`, and the census bounds every read.

        The read asks for one byte more than the size stated, which shows the object is larger without reading it, and
        only this refusal looks the size held up, for the operator's message.
        """
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        large = b"x" * 4096
        await blob_store.store_blob(data=large)
        storage.sized_keys.clear()

        with pytest.raises(RunnerRequestError) as exc_info:
            await read_request_tree(document=_hash_map({"large.bin": (large, 10)}), blob_store=blob_store, label="The `files` map", field="files")

        problem = problem_of(exc_info.value)
        assert problem["status"] == 422
        assert problem["code"] == "request.invalid"
        assert problem["params"] == {"field": "files"}
        # The hash and the size held ride the operator's message alone.
        assert f"{sha256_hex(large)} (held at 4096 bytes)" in problem["diagnostics"]["message"]
        assert storage.head_reads == [(_blob_key(large), 11)]
        assert storage.sized_keys == [_blob_key(large)]
        assert storage.loaded_keys == []

    async def test_a_blob_held_smaller_than_stated_is_refused_with_no_lookup(self) -> None:
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        small = b"a few bytes"
        await blob_store.store_blob(data=small)
        storage.sized_keys.clear()

        with pytest.raises(RunnerRequestError) as exc_info:
            await read_request_tree(document=_hash_map({"small.txt": (small, 100)}), blob_store=blob_store, label="The `files` map", field="files")

        problem = problem_of(exc_info.value)
        assert problem["code"] == "request.invalid"
        assert f"{sha256_hex(small)} (held at {len(small)} bytes)" in problem["diagnostics"]["message"]
        assert storage.head_reads == [(_blob_key(small), 101)]
        assert storage.sized_keys == []

    async def test_each_blob_a_request_names_is_read_in_one_request(self) -> None:
        """No size is looked up before a read: the read itself shows the length, which the hash then checks."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        contents = {f"file_{index_file}.txt": f"content {index_file}".encode() for index_file in range(5)}
        for data in contents.values():
            storage.objects[_blob_key(data)] = data

        tree = await read_request_tree(
            document=_hash_map({tree_path: (data, len(data)) for tree_path, data in contents.items()}),
            blob_store=blob_store,
            label="The map",
            field="files",
        )

        assert tree == RequestTree.make_from_contents(contents=contents)
        assert sorted(storage.head_reads) == sorted((_blob_key(data), len(data) + 1) for data in contents.values())
        assert storage.sized_keys == []
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

    @pytest.mark.parametrize(
        ("entries", "expected_code", "expected_params"),
        [
            pytest.param(
                {"inputs.json": _HASH_HELD_AT_ANOTHER_SIZE, "main.mthds": "x"},
                "method.package_invalid",
                {"reason": "excluded_name", "path": "inputs.json"},
                id="a key the membership rule never admits, holding the hash",
            ),
            pytest.param(
                {"templates\\card.html": _HASH_HELD_AT_ANOTHER_SIZE, "main.mthds": "x"},
                "method.package_invalid",
                {"reason": "invalid_tree_path", "path": "templates\\card.html"},
                id="a key that is not a tree path, holding the hash",
            ),
            pytest.param(
                {"README.md": "a", "readme.md": "b", "card.html": _HASH_HELD_AT_ANOTHER_SIZE},
                "method.package_invalid",
                {"reason": "path_collision", "path": "README.md"},
                id="colliding keys beside the hash",
            ),
            pytest.param(
                {"notes.txt": {"base64": "e30"}, "card.html": _HASH_HELD_AT_ANOTHER_SIZE},
                "request.invalid",
                {"field": "files"},
                id="a malformed entry beside the hash",
            ),
        ],
    )
    async def test_a_map_the_standard_refuses_for_a_key_or_an_entry_is_refused_for_it_before_any_blob_is_read(
        self, entries: dict[str, Any], expected_code: str, expected_params: dict[str, Any]
    ) -> None:
        """The bytes a hash entry names are checked last, so a map breaking another rule is refused for it, reading no blob.

        MTHDS Protocol 2.0.1 checks a map's keys, then the entries of the keys it admits, and whether the runner holds the
        bytes a hash entry names only for a map that breaks no other rule. The blob here is held at another size than its
        entry states, which a map breaking no other rule answers as `request.invalid` naming the size held: none of these
        maps gets that answer, and the blob store is never read.
        """
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        await blob_store.store_blob(data=_LARGE_BLOB)
        storage.sized_keys.clear()

        with pytest.raises(PipelexError) as exc_info:
            await read_request_tree(document=json.dumps(entries), blob_store=blob_store, label="The `files` map", field="files")

        problem = problem_of(exc_info.value)
        assert problem["status"] == 422
        assert problem["code"] == expected_code
        assert problem["params"] == expected_params
        assert "(held at" not in problem["diagnostics"]["message"]
        assert storage.head_reads == []
        assert storage.sized_keys == []
        assert storage.loaded_keys == []

    async def test_a_damaged_blob_beside_a_refused_key_is_never_read(self) -> None:
        """A map refused for a key is answered for it, a 422, even when a blob it names is damaged in storage, a 500."""
        storage = _CountingStorage()
        blob_store = RunnerBlobStore(scope=_SCOPE, storage=storage, scheme="memory")
        data = b"the true bytes"
        storage.objects[_blob_key(data)] = b"the damaged!!!"
        document = _hash_map({"inputs.json": (data, len(data)), "card.html": (data, len(data))})

        with pytest.raises(RequestMethodError) as exc_info:
            await read_request_tree(document=document, blob_store=blob_store, label="The `files` map", field="files")

        problem = problem_of(exc_info.value)
        assert problem["code"] == "method.package_invalid"
        assert problem["params"] == {"reason": "excluded_name", "path": "inputs.json"}
        assert storage.head_reads == []

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
        blobs = [f"file number {index_blob}".encode() for index_blob in range(3 * max(MAX_CONCURRENT_BLOB_LOOKUPS, MAX_CONCURRENT_BLOB_READS))]
        for data in blobs:
            storage.objects[_blob_key(data)] = data

        stored = await blob_store.stored_sizes(sha256s=[sha256_hex(data) for data in blobs])
        stated = await blob_store.read_stated(stated_sizes={sha256_hex(data): {len(data)} for data in blobs})

        assert stored == {sha256_hex(data): len(data) for data in blobs}
        assert [stated.held.read_blob(sha256_hex(data)) for data in blobs] == blobs
        assert stated.mismatched == {}
        assert storage.most_lookups_at_once == MAX_CONCURRENT_BLOB_LOOKUPS
        assert storage.most_loads_at_once == MAX_CONCURRENT_BLOB_READS

    async def test_the_s3_client_pool_holds_every_request_a_blob_store_runs_at_once(self) -> None:
        """The S3 provider shares one client per loop, so a pool smaller than these would queue a request's own reads."""
        assert max(MAX_CONCURRENT_BLOB_LOOKUPS, MAX_CONCURRENT_BLOB_READS) <= S3_MAX_POOL_CONNECTIONS

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
            ("azure", "plugin"),
        ],
    )
    def test_the_problem_names_the_kind_of_storage_as_the_registry_spells_it(self, storage_method: str, scheme: str) -> None:
        assert problem_scheme_of(storage_method=storage_method) == scheme
        params = problem_of(BlobStoreDamagedError("damaged", scheme=scheme)).get("params")
        assert params == {"scheme": scheme}
