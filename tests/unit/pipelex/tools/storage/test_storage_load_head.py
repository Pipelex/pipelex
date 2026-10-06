"""The default head read every storage provider inherits: the whole object, sliced.

A provider that can read a byte range (S3, GCS) overrides it; one that cannot, including an external
storage plugin written before the head read existed, keeps working through this default.
"""

from pathlib import Path

import pytest

from pipelex.tools.storage.exceptions import StorageFileNotFoundError
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.storage.local_storage_provider import LocalStorageProvider
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME

PAYLOAD = b"%PDF-1.7\n" + b"x" * 20_000


@pytest.mark.asyncio(loop_scope="class")
class TestDefaultLoadHead:
    async def test_in_memory_head_is_the_first_bytes(self) -> None:
        provider = InMemoryStorageProvider()
        uri = await provider.store(data=PAYLOAD, key="head/file.pdf")

        head = await provider.load_head(uri=uri, nb_bytes=8192)

        assert head == PAYLOAD[:8192]

    async def test_local_head_is_the_first_bytes(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)
        uri = await provider.store(data=PAYLOAD, key="head/file.pdf")

        head = await provider.load_head(uri=uri, nb_bytes=8192)

        assert head == PAYLOAD[:8192]

    async def test_a_head_longer_than_the_object_is_the_whole_object(self) -> None:
        provider = InMemoryStorageProvider()
        uri = await provider.store(data=b"short", key="head/short.txt")

        assert await provider.load_head(uri=uri, nb_bytes=8192) == b"short"

    async def test_a_missing_object_raises_not_found(self, tmp_path: Path) -> None:
        provider = LocalStorageProvider(root_path=tmp_path)

        with pytest.raises(StorageFileNotFoundError):
            await provider.load_head(uri=f"{PIPELEX_STORAGE_SCHEME}missing/file.pdf", nb_bytes=8192)
