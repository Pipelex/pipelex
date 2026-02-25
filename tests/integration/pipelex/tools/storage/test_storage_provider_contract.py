"""Tests that verify storage providers implement the full contract.

These tests document the requirements that any storage provider (including
future S3/GCP implementations) must satisfy to work with ImageContent.

When implementing a new storage provider, ensure all these tests pass.

Storage Provider Contract Requirements:

- store(data: bytes, key: str) -> str: Must return a pipelex-storage:// URI
- load(uri: str) -> bytes: Must load data from a pipelex-storage:// URI
- public_url(uri: str) -> str | None: Must return a human-readable link or None
"""

import pytest

from pipelex.tools.misc.file_utils import load_binary
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract
from tests.cases import ImageTestCases


@pytest.mark.asyncio(loop_scope="class")
class TestStorageProviderContract:
    """Tests that verify storage providers implement the full contract.

    These tests document the requirements that any storage provider (including
    future S3/GCP implementations) must satisfy to work with ImageContent.

    When implementing a new storage provider, ensure all these tests pass.
    """

    async def test_store_returns_pipelex_storage_uri(
        self,
        storage_provider: StorageProviderAbstract,
    ) -> None:
        """Contract: store() must return a URI with pipelex-storage:// scheme.

        This is critical because the entire image flow depends on recognizing
        pipelex-storage:// URIs to route them to the storage provider.
        """
        test_data = b"contract test data"
        key = "contract/test.bin"

        uri = await storage_provider.store(data=test_data, key=key)

        assert uri.startswith(PIPELEX_STORAGE_SCHEME)
        assert uri == f"{PIPELEX_STORAGE_SCHEME}{key}"

    async def test_load_retrieves_stored_data(
        self,
        storage_provider: StorageProviderAbstract,
    ) -> None:
        """Contract: load() must retrieve exactly the data that was stored.

        Data integrity is essential for image handling. The bytes retrieved
        must be identical to the bytes stored.
        """
        # Use real image data for a realistic test
        image_bytes = load_binary(path=ImageTestCases.IMAGE_FILE_PATH_LOGO_TINY)
        key = "contract/image.png"

        uri = await storage_provider.store(data=image_bytes, key=key)
        retrieved = await storage_provider.load(uri=uri)

        assert retrieved == image_bytes

    async def test_public_url_returns_string_or_none(
        self,
        storage_provider: StorageProviderAbstract,
    ) -> None:
        """Contract: public_url() must return either a string or None.

        - Local storage: Returns file:// URI for terminal clickability
        - In-memory storage: Returns None (no persistent location)
        - S3/GCP storage: Should return https:// URL or signed URL

        This behavior must be documented for each storage type.
        """
        test_data = b"display link test"
        key = "contract/display.bin"

        uri = await storage_provider.store(data=test_data, key=key)
        display = await storage_provider.public_url(uri=uri)

        # Must be string or None
        assert display is None or isinstance(display, str)

        # If string, it should be a valid link format
        if display is not None:
            assert len(display) > 0

    async def test_handles_nested_key_paths(
        self,
        storage_provider: StorageProviderAbstract,
    ) -> None:
        """Contract: store() must handle nested key paths with forward slashes.

        The uri_format uses paths like "{primary_id}/{secondary_id}/{hash}.{extension}"
        which creates nested directories/paths. Storage providers must support this.
        """
        test_data = b"nested path test"
        key = "level1/level2/level3/file.png"

        uri = await storage_provider.store(data=test_data, key=key)
        retrieved = await storage_provider.load(uri=uri)

        assert retrieved == test_data

    async def test_handles_overwrite(
        self,
        storage_provider: StorageProviderAbstract,
    ) -> None:
        """Contract: store() with same key must overwrite existing data.

        This is important for regenerating images or retrying failed operations.
        """
        key = "contract/overwrite.png"
        original = b"original data"
        updated = b"updated data"

        await storage_provider.store(data=original, key=key)
        uri = await storage_provider.store(data=updated, key=key)
        retrieved = await storage_provider.load(uri=uri)

        assert retrieved == updated

    async def test_handles_empty_data(
        self,
        storage_provider: StorageProviderAbstract,
    ) -> None:
        """Contract: store() and load() must handle empty bytes.

        While unusual for images, edge cases should be handled gracefully.
        """
        key = "contract/empty.bin"

        uri = await storage_provider.store(data=b"", key=key)
        retrieved = await storage_provider.load(uri=uri)

        assert retrieved == b""

    async def test_handles_large_binary_data(
        self,
        storage_provider: StorageProviderAbstract,
    ) -> None:
        """Contract: store() and load() must handle larger binary data.

        Images can be several megabytes. This test uses ~256KB to verify
        the provider handles non-trivial data sizes.
        """
        # ~256KB of binary data
        large_data = bytes(range(256)) * 1000
        key = "contract/large.bin"

        uri = await storage_provider.store(data=large_data, key=key)
        retrieved = await storage_provider.load(uri=uri)

        assert retrieved == large_data
        assert len(retrieved) == len(large_data)
