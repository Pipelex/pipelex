"""The size read every storage provider offers: from metadata where it can, else by loading the object.

A provider that can read an object's size without its bytes (local, in memory, S3, GCS) overrides it; one that cannot,
including an external storage plugin written before the size read existed, keeps working through the default.
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.errors.problem import ProblemView
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.tools.storage.exceptions import StorageFileNotFoundError, StorageLocalError
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract, StoredData

PAYLOAD = b"%PDF-1.7\n" + b"x" * 20_000


class _LoadOnlyProvider(StorageProviderAbstract):
    """A provider implementing only the abstract reads and writes, as an older external plugin does."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    @override
    async def _load_with_metadata(self, key: str) -> StoredData:
        if key not in self.objects:
            msg = f"File not found: '{key}'"
            raise StorageFileNotFoundError(msg)
        return StoredData(data=self.objects[key], mime_type=None)

    @override
    async def _store(self, data: bytes, *, key: str, content_type: str | None, checksum_sha256_hex: str | None) -> None:
        self.objects[key] = data

    @override
    async def public_url(self, uri: str) -> str | None:
        return None


@pytest.mark.asyncio(loop_scope="class")
class TestStorageLoadSize:
    async def test_every_provider_reads_the_size_of_what_it_stored(self, tmp_path: Path) -> None:
        for provider in [InMemoryStorageProvider(), LocalStorageProvider(root_path=tmp_path), _LoadOnlyProvider()]:
            uri = await provider.store(data=PAYLOAD, key="size/file.pdf")

            assert await provider.load_size(uri=uri) == len(PAYLOAD)

    async def test_a_missing_object_raises_not_found(self, tmp_path: Path) -> None:
        for provider in [InMemoryStorageProvider(), LocalStorageProvider(root_path=tmp_path), _LoadOnlyProvider()]:
            with pytest.raises(StorageFileNotFoundError):
                await provider.load_size(uri=f"{PIPELEX_STORAGE_SCHEME}missing/file.pdf")

    async def test_a_missing_object_names_the_kind_of_storage_that_lost_it(self, tmp_path: Path) -> None:
        """The refusal of a provider Pipelex ships names its kind, the `scheme` of `pipelex.storage.not_found`."""
        for provider, expected_kind in [(InMemoryStorageProvider(), "memory"), (LocalStorageProvider(root_path=tmp_path), "local")]:
            for read in (
                provider.load(uri=f"{PIPELEX_STORAGE_SCHEME}missing/file.pdf"),
                provider.load_size(uri=f"{PIPELEX_STORAGE_SCHEME}missing/file.pdf"),
            ):
                with pytest.raises(StorageFileNotFoundError) as raised:
                    await read
                problem = raised.value.to_problem(view=ProblemView.CALLER)
                assert problem.code == PipelexErrorCode.STORAGE_NOT_FOUND
                assert problem.params is not None
                assert problem.params.as_wire() == {"scheme": expected_kind}

    async def test_the_local_size_is_read_without_opening_the_file(self, tmp_path: Path, mocker: MockerFixture) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        uri = await provider.store(data=PAYLOAD, key="size/file.pdf")
        opened = mocker.patch("pipelex.tools.storage.local_storage_provider.aiofiles.open")

        assert await provider.load_size(uri=uri) == len(PAYLOAD)
        opened.assert_not_called()

    async def test_a_local_key_naming_a_directory_is_a_local_storage_error(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        (tmp_path / "a_directory").mkdir()

        with pytest.raises(StorageLocalError, match="a_directory"):
            await provider.load_size(uri=f"{PIPELEX_STORAGE_SCHEME}a_directory")
