import asyncio
import errno
import hashlib
from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.tools.storage.exceptions import StorageChecksumMismatchError, StorageFileNotFoundError, StorageInvalidKeyError, StorageLocalError
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract, StoredData

PAYLOAD = b"the bytes a blob holds"
OTHER_PAYLOAD = b"other bytes, under the same key"
KEY = "scope/blobs/one"


class _PlainProvider(StorageProviderAbstract):
    """A provider implementing only the abstract reads and writes, as an external plugin may."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.checksums: dict[str, str | None] = {}

    @override
    async def _load_with_metadata(self, key: str) -> StoredData:
        if key not in self.objects:
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg)
        return StoredData(data=self.objects[key], mime_type=None)

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> None:
        self.objects[key] = data
        self.checksums[key] = checksum_sha256_hex

    @override
    async def public_url(self, uri: str) -> str | None:
        return None


def _providers(*, tmp_path: Path) -> list[StorageProviderAbstract]:
    return [InMemoryStorageProvider(), LocalStorageProvider(root_path=tmp_path), _PlainProvider()]


@pytest.mark.asyncio(loop_scope="class")
class TestStorageStoreIfAbsent:
    async def test_a_free_key_is_created_and_a_held_one_is_never_replaced(self, tmp_path: Path) -> None:
        for provider in _providers(tmp_path=tmp_path):
            assert await provider.store_if_absent(data=PAYLOAD, key=KEY) is True
            assert await provider.store_if_absent(data=OTHER_PAYLOAD, key=KEY) is False

            assert await provider.load(uri=f"{PIPELEX_STORAGE_SCHEME}{KEY}") == PAYLOAD

    async def test_bytes_matching_their_checksum_are_created(self, tmp_path: Path) -> None:
        for provider in _providers(tmp_path=tmp_path):
            created = await provider.store_if_absent(data=PAYLOAD, key=KEY, checksum_sha256_hex=hashlib.sha256(PAYLOAD).hexdigest())

            assert created is True
            assert await provider.load(uri=f"{PIPELEX_STORAGE_SCHEME}{KEY}") == PAYLOAD

    async def test_the_default_hands_the_checksum_on_to_the_plain_store(self) -> None:
        """A provider overriding only `_store` still receives the checksum, for a storage that can check it."""
        provider = _PlainProvider()
        sha256 = hashlib.sha256(PAYLOAD).hexdigest()

        assert await provider.store_if_absent(data=PAYLOAD, key=KEY, checksum_sha256_hex=sha256) is True

        assert provider.checksums == {KEY: sha256}

    async def test_bytes_not_matching_their_checksum_are_refused_before_any_write(self, tmp_path: Path) -> None:
        for provider in _providers(tmp_path=tmp_path):
            with pytest.raises(StorageChecksumMismatchError, match="do not hash to the checksum"):
                await provider.store_if_absent(data=PAYLOAD, key=KEY, checksum_sha256_hex=hashlib.sha256(OTHER_PAYLOAD).hexdigest())

            with pytest.raises(StorageFileNotFoundError):
                await provider.load_size(uri=f"{PIPELEX_STORAGE_SCHEME}{KEY}")

    async def test_a_key_carrying_the_scheme_is_refused(self, tmp_path: Path) -> None:
        for provider in _providers(tmp_path=tmp_path):
            with pytest.raises(StorageInvalidKeyError):
                await provider.store_if_absent(data=PAYLOAD, key=f"{PIPELEX_STORAGE_SCHEME}{KEY}")

    async def test_of_two_local_writers_of_one_key_exactly_one_creates_it(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)

        outcomes = await asyncio.gather(
            provider.store_if_absent(data=PAYLOAD, key=KEY),
            provider.store_if_absent(data=OTHER_PAYLOAD, key=KEY),
        )

        assert sorted(outcomes) == [False, True]
        held = (tmp_path / KEY).read_bytes()
        assert held == (PAYLOAD if outcomes[0] else OTHER_PAYLOAD)
        assert [path.name for path in (tmp_path / KEY).parent.iterdir()] == ["one"]

    async def test_a_local_create_leaves_no_temporary_file(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)

        await provider.store_if_absent(data=PAYLOAD, key=KEY)
        await provider.store_if_absent(data=OTHER_PAYLOAD, key=KEY)

        assert [path.name for path in (tmp_path / KEY).parent.iterdir()] == ["one"]

    async def test_a_filesystem_refusing_the_hard_link_is_a_local_storage_error(self, tmp_path: Path, mocker: MockerFixture) -> None:
        """A filesystem that cannot make a hard link cannot create a file only when its name is free: the write fails loudly."""
        provider = LocalStorageProvider(root_path=tmp_path)
        mocker.patch.object(Path, "hardlink_to", autospec=True, side_effect=OSError(errno.EPERM, "Operation not permitted"))

        with pytest.raises(StorageLocalError, match="Operation not permitted"):
            await provider.store_if_absent(data=PAYLOAD, key=KEY)

        assert not (tmp_path / KEY).exists()
        assert list((tmp_path / KEY).parent.iterdir()) == []

    async def test_a_key_through_a_file_is_a_local_storage_error_not_a_key_held(self, tmp_path: Path) -> None:
        """A file standing where a folder of the key should be fails the temporary file's folder, which is no key held."""
        provider = LocalStorageProvider(root_path=tmp_path)
        (tmp_path / "scope").write_bytes(b"a file where a folder should be")

        with pytest.raises(StorageLocalError, match="Failed to create file 'scope/blobs/one'"):
            await provider.store_if_absent(data=PAYLOAD, key="scope/blobs/one")

        with pytest.raises(StorageLocalError, match="Failed to create file 'scope/one'"):
            await provider.store_if_absent(data=PAYLOAD, key="scope/one")

        assert (tmp_path / "scope").read_bytes() == b"a file where a folder should be"

    async def test_a_folder_at_the_key_is_a_local_storage_error_not_a_key_held(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        (tmp_path / KEY).mkdir(parents=True)

        with pytest.raises(StorageLocalError, match="not a file"):
            await provider.store_if_absent(data=PAYLOAD, key=KEY)

        assert (tmp_path / KEY).is_dir()
        assert [path.name for path in (tmp_path / KEY).parent.iterdir()] == ["one"]
