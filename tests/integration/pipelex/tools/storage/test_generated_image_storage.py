"""Integration tests for generated images with storage providers.

These tests verify the flow: GeneratedImageRawDetails -> GeneratedContentFactory -> Storage -> Retrieval

Future storage implementations (S3, GCP) must pass these tests to ensure
compatibility with AI-generated image handling.
"""

import base64
from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.image.generated_image import GeneratedImageRawDetails
from pipelex.cogt.image.image_size import ImageSize
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.image.prompt_image_utils import prepare_prompt_image
from pipelex.tools.misc.file_utils import load_binary
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME, StorageProviderAbstract
from pipelex.tools.uri.prepared_file import PreparedFileBase64
from tests.cases import ImageTestCases


@pytest.mark.asyncio(loop_scope="class")
class TestGeneratedImageStorage:
    """Integration tests for generated images with storage providers.

    These tests verify the flow: GeneratedImageRawDetails -> GeneratedContentFactory -> Storage -> Retrieval

    Future storage implementations (S3, GCP) must pass these tests to ensure
    compatibility with AI-generated image handling.
    """

    async def test_generated_image_from_bytes(
        self,
        generated_content_factory: GeneratedContentFactory,
        mocker: MockerFixture,
        storage_provider: StorageProviderAbstract,
    ) -> None:
        """Test GeneratedContentFactory stores images from raw bytes correctly.

        This simulates the flow when an image generation API returns raw bytes
        (e.g., from a PIL image or binary response).
        """
        # Mock get_storage_provider for the retrieval step
        mocker.patch("pipelex.cogt.image.prompt_image_utils.get_storage_provider", return_value=storage_provider)

        # Load a real test image as bytes
        image_bytes = load_binary(path=Path(ImageTestCases.IMAGE_FILE_PATH_LOGO_TINY))

        # Create GeneratedImageRawDetails with raw bytes
        raw_details = GeneratedImageRawDetails(
            size=ImageSize(width=18, height=18),
            actual_bytes=image_bytes,
            mime_type="image/png",
        )

        # Generate ImageContent via factory
        image_content = await generated_content_factory.make_image_content(
            storage_scope="test/scope",
            raw_details=raw_details,
        )

        # Verify the URL is a pipelex-storage:// URI
        assert image_content.url.startswith(PIPELEX_STORAGE_SCHEME)

        # Verify roundtrip: storage -> PreparedImage
        prompt_image = PromptImageFactory.make_prompt_image(uri=image_content.url)
        prepared = await prepare_prompt_image(
            prompt_image=prompt_image,
            is_http_url_enabled=False,
        )

        assert isinstance(prepared, PreparedFileBase64)
        # Verify the data matches the original
        decoded = base64.b64decode(prepared.base64_data)
        assert decoded == image_bytes

    async def test_generated_image_from_base64(
        self,
        generated_content_factory: GeneratedContentFactory,
        mocker: MockerFixture,
        storage_provider: StorageProviderAbstract,
    ) -> None:
        """Test GeneratedContentFactory stores images from base64 strings correctly.

        This simulates the flow when an image generation API returns a base64-encoded
        image string (common with OpenAI, Stability AI, etc.).
        """
        # Mock get_storage_provider for the retrieval step
        mocker.patch("pipelex.cogt.image.prompt_image_utils.get_storage_provider", return_value=storage_provider)

        # Create GeneratedImageRawDetails with base64 string
        raw_details = GeneratedImageRawDetails(
            size=ImageSize(width=1, height=1),
            base64_str=ImageTestCases.MINIMAL_PNG_BASE64,
            mime_type="image/png",
        )

        # Generate ImageContent via factory
        image_content = await generated_content_factory.make_image_content(
            storage_scope="test/scope",
            raw_details=raw_details,
        )

        # Verify the URL is a pipelex-storage:// URI
        assert image_content.url.startswith(PIPELEX_STORAGE_SCHEME)

        # Verify roundtrip: storage -> PreparedImage
        prompt_image = PromptImageFactory.make_prompt_image(uri=image_content.url)
        prepared = await prepare_prompt_image(
            prompt_image=prompt_image,
            is_http_url_enabled=False,
        )

        assert isinstance(prepared, PreparedFileBase64)
        assert prepared.base64_data == ImageTestCases.MINIMAL_PNG_BASE64

    async def test_generated_image_uri_format_applied(
        self,
        generated_content_factory: GeneratedContentFactory,
    ) -> None:
        """Test that the uri_format from config is correctly applied.

        Each storage method has its own uri_format configured. This test verifies
        that the format is used when building storage keys.
        """
        # Create GeneratedImageRawDetails
        raw_details = GeneratedImageRawDetails(
            size=ImageSize(width=1, height=1),
            base64_str=ImageTestCases.MINIMAL_PNG_BASE64,
            mime_type="image/png",
        )

        # Generate ImageContent
        image_content = await generated_content_factory.make_image_content(
            storage_scope="test/scope",
            raw_details=raw_details,
        )

        # Extract the key from the URI (remove scheme prefix)
        storage_key = image_content.url.removeprefix(PIPELEX_STORAGE_SCHEME)

        # Verify the key follows the uri_format pattern: "{storage_scope}/{hash}.{extension}".
        # It used to assert a pipeline id and a step id, from the `{primary_id}`/
        # `{secondary_id}` layout — keying generated bytes by WHICH RUN produced
        # them, which is exactly the coupling `storage_scope` replaces.
        assert storage_key.startswith("test/scope/")
        assert storage_key.endswith(".png")
