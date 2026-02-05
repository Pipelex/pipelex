"""Integration tests for the full pipelex-storage:// image flow.

These tests verify the complete flow:
1. Store an image via StorageProvider
2. Create ImageContent with pipelex-storage:// URI
3. Convert to PromptImage via factory
4. Prepare via prep_prompt_images() for each provider type
5. Verify all return valid PreparedImage
"""

import base64

import pytest
import pytest_asyncio
from pytest_mock import MockerFixture

from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.image.prompt_image_utils import prep_prompt_images, prepare_prompt_image
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.tools.misc.file_utils import load_binary
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.uri.prepared_file import PreparedFileBase64
from pipelex.tools.uri.resolved_uri import ResolvedPipelexStorage
from pipelex.tools.uri.uri_resolver import resolve_uri

# Test image path from test data
TEST_IMAGE_PATH = "tests/data/images/eiffel_tower.png"


@pytest_asyncio.fixture
async def storage_provider_with_test_image() -> tuple[InMemoryStorageProvider, str]:
    """Create an in-memory storage with a real test image and return (provider, uri)."""
    provider = InMemoryStorageProvider()
    # Load a real test image
    image_bytes = load_binary(path=TEST_IMAGE_PATH)
    key = "pipeline_run_123/generated_image.png"
    uri = await provider.store(data=image_bytes, key=key)
    return provider, uri


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestPipelexStorageImageFlow:
    """Integration tests for the full pipelex-storage:// image flow."""

    async def test_full_flow_storage_to_prepared_image(
        self,
        mocker: MockerFixture,
        storage_provider_with_test_image: tuple[InMemoryStorageProvider, str],
    ) -> None:
        """Test the complete flow from storage to PreparedImage.

        This simulates the real-world scenario where:
        1. An image generator stores an image → returns pipelex-storage:// URI
        2. That URI becomes an ImageContent.url
        3. User passes ImageContent to an LLM pipe as input
        4. The LLM pipe converts ImageContent → PromptImage → PreparedImage
        """
        provider, storage_uri = storage_provider_with_test_image

        # Mock get_storage_provider to return our in-memory provider
        mocker.patch("pipelex.cogt.image.prompt_image_utils.get_storage_provider", return_value=provider)

        # Step 1: Create ImageContent as would be returned by GeneratedContentFactory
        image_content = ImageContent(
            url=storage_uri,
            public_url=None,
            mime_type="image/png",
        )

        # Step 2: Convert to PromptImage via factory (as done in llm_prompt_blueprint.py)
        prompt_image = PromptImageFactory.make_prompt_image(uri=image_content.url)
        assert isinstance(prompt_image, PromptImageUri)

        # Step 3: Prepare for LLM API consumption
        prepared = await prepare_prompt_image(
            prompt_image=prompt_image,
            is_http_url_enabled=False,
        )

        # Verify result
        assert isinstance(prepared, PreparedFileBase64)
        assert prepared.file_type.mime == "image/png"
        # Verify base64 data is valid (can be decoded)
        decoded = base64.b64decode(prepared.base64_data)
        assert len(decoded) > 0

    async def test_prep_prompt_images_batch_with_storage_uri(
        self,
        mocker: MockerFixture,
        storage_provider_with_test_image: tuple[InMemoryStorageProvider, str],
    ) -> None:
        """Test batch preparation of multiple images including pipelex-storage:// URIs."""
        provider, storage_uri = storage_provider_with_test_image

        # Mock get_storage_provider
        mocker.patch("pipelex.cogt.image.prompt_image_utils.get_storage_provider", return_value=provider)

        # Create multiple PromptImages: one from storage, one from local path
        prompt_images = [
            PromptImageFactory.make_prompt_image(uri=storage_uri),
            PromptImageFactory.make_prompt_image(uri=TEST_IMAGE_PATH),
        ]

        # Prepare all images in parallel
        prepared_images = await prep_prompt_images(
            prompt_images=prompt_images,
            is_http_url_enabled=False,
        )

        # Verify all images were prepared
        assert len(prepared_images) == 2
        for prepared in prepared_images:
            assert isinstance(prepared, PreparedFileBase64)
            assert prepared.file_type.mime == "image/png"

    async def test_storage_uri_resolves_correctly(
        self,
        storage_provider_with_test_image: tuple[InMemoryStorageProvider, str],
    ) -> None:
        """Test that pipelex-storage:// URIs are correctly resolved."""
        _, storage_uri = storage_provider_with_test_image

        resolved = resolve_uri(storage_uri)

        assert isinstance(resolved, ResolvedPipelexStorage)
        assert resolved.storage_uri == storage_uri

    async def test_prompt_image_uri_caches_resolved(
        self,
        storage_provider_with_test_image: tuple[InMemoryStorageProvider, str],
    ) -> None:
        """Test that PromptImageUri.resolved property caches the ResolvedUri."""
        _, storage_uri = storage_provider_with_test_image

        prompt_image = PromptImageUri(uri=storage_uri)

        # Access .resolved twice and verify it's the same instance (cached)
        resolved1 = prompt_image.resolved
        resolved2 = prompt_image.resolved

        assert isinstance(resolved1, ResolvedPipelexStorage)
        assert resolved1 is resolved2  # Same instance due to caching
