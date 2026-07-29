"""Unit tests for pipelex-storage:// URI support in LLM provider plugins.

These tests verify that all plugins can handle images stored via pipelex-storage:// URIs.
"""

import pytest
import pytest_asyncio
from google.genai import types as genai_types
from mistralai.models import ImageURLChunk
from pytest_mock import MockerFixture

from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.image.prompt_image_utils import prepare_prompt_image_as_base64
from pipelex.providers.google.google_factory import GoogleFactory
from pipelex.providers.mistral.mistral_factory import MistralFactory
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.uri.prepared_file import PreparedFileBase64

# Minimal PNG image (1x1 transparent pixel)
MINIMAL_PNG_BYTES = bytes(
    [
        0x89,
        0x50,
        0x4E,
        0x47,
        0x0D,
        0x0A,
        0x1A,
        0x0A,  # PNG signature
        0x00,
        0x00,
        0x00,
        0x0D,
        0x49,
        0x48,
        0x44,
        0x52,  # IHDR chunk
        0x00,
        0x00,
        0x00,
        0x01,
        0x00,
        0x00,
        0x00,
        0x01,  # 1x1
        0x08,
        0x06,
        0x00,
        0x00,
        0x00,
        0x1F,
        0x15,
        0xC4,
        0x89,  # 8-bit RGBA
        0x00,
        0x00,
        0x00,
        0x0A,
        0x49,
        0x44,
        0x41,
        0x54,  # IDAT chunk
        0x78,
        0x9C,
        0x63,
        0x00,
        0x01,
        0x00,
        0x00,
        0x05,
        0x00,
        0x01,
        0x0D,
        0x0A,
        0x2D,
        0xB4,  # compressed data
        0x00,
        0x00,
        0x00,
        0x00,
        0x49,
        0x45,
        0x4E,
        0x44,  # IEND chunk
        0xAE,
        0x42,
        0x60,
        0x82,  # CRC
    ]
)


@pytest_asyncio.fixture
async def storage_with_image() -> tuple[InMemoryStorageProvider, str]:
    """Create an in-memory storage with a test image and return (provider, uri)."""
    provider = InMemoryStorageProvider()
    key = "test_images/sample.png"
    uri = await provider.store(data=MINIMAL_PNG_BYTES, key=key)
    return provider, uri


@pytest.fixture
def prompt_image_with_storage_uri(storage_with_image: tuple[InMemoryStorageProvider, str]) -> PromptImageUri:
    """Create a PromptImageUri pointing to a pipelex-storage:// URI."""
    _, uri = storage_with_image
    return PromptImageUri(uri=uri)


class TestGoogleFactoryPipelexStorageSupport:
    """Tests for GoogleFactory handling of pipelex-storage:// URIs."""

    @pytest.mark.asyncio
    async def test_prepare_image_part_with_pipelex_storage_uri(
        self,
        mocker: MockerFixture,
        storage_with_image: tuple[InMemoryStorageProvider, str],
        prompt_image_with_storage_uri: PromptImageUri,
    ) -> None:
        """Test that GoogleFactory.prepare_image_part() handles pipelex-storage:// URIs.

        Currently EXPECTED TO FAIL - raises GoogleFactoryError.
        After refactoring, this should return a valid genai Part.
        """
        provider, _ = storage_with_image

        # Mock get_storage_provider to return our in-memory provider
        mocker.patch("pipelex.cogt.image.prompt_image_utils.get_storage_provider", return_value=provider)

        # This should NOT raise an error after refactoring
        result = await GoogleFactory.prepare_image_part(prompt_image_with_storage_uri)

        assert isinstance(result, genai_types.Part)


class TestMistralFactoryPipelexStorageSupport:
    """Tests for MistralFactory handling of pipelex-storage:// URIs."""

    @pytest.mark.asyncio
    async def test_make_mistral_image_url_with_pipelex_storage_uri(
        self,
        mocker: MockerFixture,
        storage_with_image: tuple[InMemoryStorageProvider, str],
        prompt_image_with_storage_uri: PromptImageUri,
    ) -> None:
        """Test that MistralFactory.make_mistral_image_url() handles pipelex-storage:// URIs.

        Currently EXPECTED TO FAIL - raises PromptImageFormatError.
        After refactoring, this should return a valid ImageURLChunk.
        """
        provider, _ = storage_with_image

        # Mock get_storage_provider to return our in-memory provider
        mocker.patch("pipelex.cogt.image.prompt_image_utils.get_storage_provider", return_value=provider)

        factory = MistralFactory()
        # This should NOT raise an error after refactoring
        result = await factory.make_mistral_image_url(prompt_image_with_storage_uri)

        assert isinstance(result, ImageURLChunk)
        # Should be a data URL since we're converting from storage
        image_url = result.image_url
        assert isinstance(image_url, str)
        assert image_url.startswith("data:image/")


class TestPromptImageUtilsPipelexStorageSupport:
    """Tests verifying that prompt_image_utils supports pipelex-storage:// correctly."""

    @pytest.mark.asyncio
    async def test_prepare_prompt_image_as_base64_with_pipelex_storage_uri(
        self,
        mocker: MockerFixture,
        storage_with_image: tuple[InMemoryStorageProvider, str],
        prompt_image_with_storage_uri: PromptImageUri,
    ) -> None:
        """Test that prepare_prompt_image_as_base64() correctly handles pipelex-storage:// URIs."""
        provider, _ = storage_with_image

        # Mock get_storage_provider to return our in-memory provider
        mocker.patch("pipelex.cogt.image.prompt_image_utils.get_storage_provider", return_value=provider)

        result = await prepare_prompt_image_as_base64(prompt_image_with_storage_uri)

        assert isinstance(result, PreparedFileBase64)
        assert result.file_type.mime == "image/png"
