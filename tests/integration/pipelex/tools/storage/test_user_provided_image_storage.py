"""Integration tests for user-provided images with storage providers.

These tests verify the flow: User Input -> normalize_data_urls_to_storage -> Storage -> Retrieval

Future storage implementations (S3, GCP) must pass these tests to ensure
compatibility with user-provided image handling.
"""

import base64

import pytest

from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.image.prompt_image_utils import prepare_prompt_image
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipeline.input_normalizer import normalize_data_urls_to_storage
from pipelex.tools.storage.storage_provider_abstract import PIPELEX_STORAGE_SCHEME
from pipelex.tools.uri.prepared_file import PreparedFileBase64
from pipelex.urls import URLs
from tests.cases import ImageTestCases


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.usefixtures("storage_provider_patched")
class TestUserProvidedImageStorage:
    """Integration tests for user-provided images with storage providers.

    These tests verify the flow: User Input -> normalize_data_urls_to_storage -> Storage -> Retrieval

    Future storage implementations (S3, GCP) must pass these tests to ensure
    compatibility with user-provided image handling.
    """

    async def test_user_image_data_url_to_storage_roundtrip(self) -> None:
        """Test that user-provided data URL images are normalized to storage and can be retrieved.

        Flow:
        1. User provides ImageContent with data:// URL
        2. normalize_data_urls_to_storage converts to pipelex-storage:// URI
        3. Image can be retrieved via PromptImageFactory -> PreparedImage
        """
        # Create ImageContent with data URL (simulating user input)
        image_content = ImageContent(url=ImageTestCases.MINIMAL_PNG_DATA_URL)
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=image_content,
            name="user_image",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize to storage
        normalized_memory = await normalize_data_urls_to_storage(working_memory)

        # Verify the URL was converted to pipelex-storage://
        normalized_stuff = normalized_memory.get_stuff("user_image")
        assert isinstance(normalized_stuff.content, ImageContent)
        assert normalized_stuff.content.url.startswith(PIPELEX_STORAGE_SCHEME)

        # Verify roundtrip: storage -> PreparedImage
        prompt_image = PromptImageFactory.make_prompt_image(uri=normalized_stuff.content.url)
        assert isinstance(prompt_image, PromptImageUri)

        prepared = await prepare_prompt_image(
            prompt_image=prompt_image,
            is_http_url_enabled=False,
        )

        assert isinstance(prepared, PreparedFileBase64)
        # Verify the data matches the original
        assert prepared.base64_data == ImageTestCases.MINIMAL_PNG_BASE64

    async def test_user_image_local_file_to_prepared(self) -> None:
        """Test that user-provided local file paths work through the image flow.

        Local file paths are not normalized to storage but should still work
        when converted to PreparedImage for LLM consumption.
        """
        # Create ImageContent with local file path
        local_path = ImageTestCases.IMAGE_FILE_PATH_LOGO_TINY
        image_content = ImageContent(url=local_path)

        # Convert to PreparedImage (bypassing normalization since local paths aren't data URLs)
        prompt_image = PromptImageFactory.make_prompt_image(uri=image_content.url)
        prepared = await prepare_prompt_image(
            prompt_image=prompt_image,
            is_http_url_enabled=False,
        )

        assert isinstance(prepared, PreparedFileBase64)
        assert prepared.file_type.mime == "image/png"
        # Verify the data can be decoded
        decoded = base64.b64decode(prepared.base64_data)
        assert len(decoded) > 0

    @pytest.mark.usefixtures("mock_fetch_remote_content_disabled")
    async def test_user_image_http_url_passthrough_when_fetch_disabled(self) -> None:
        """Test that HTTP URLs are passed through when fetch is disabled.

        When is_fetch_remote_content_enabled=False, HTTP URLs should not be
        fetched and stored. They should be passed through unchanged.
        """
        # Create ImageContent with HTTP URL
        http_url = URLs.png_example_1
        image_content = ImageContent(url=http_url)
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=image_content,
            name="remote_image",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize (should not change HTTP URLs when fetch is disabled)
        normalized_memory = await normalize_data_urls_to_storage(working_memory)

        # Verify URL was NOT changed
        normalized_stuff = normalized_memory.get_stuff("remote_image")
        assert isinstance(normalized_stuff.content, ImageContent)
        assert normalized_stuff.content.url == http_url

    @pytest.mark.usefixtures("mock_upload_local_content_enabled")
    async def test_user_image_local_file_to_storage_when_upload_enabled(self) -> None:
        """Test that local file paths are uploaded to storage when upload is enabled.

        When is_upload_local_content_enabled=True, local file paths should be read,
        uploaded to storage, and replaced with pipelex-storage:// URIs.
        """
        local_path = ImageTestCases.IMAGE_FILE_PATH_LOGO_TINY
        image_content = ImageContent(url=local_path)
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=image_content,
            name="local_image",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize - should upload the local file to storage
        normalized_memory = await normalize_data_urls_to_storage(working_memory)

        # Verify the URL was converted to pipelex-storage://
        normalized_stuff = normalized_memory.get_stuff("local_image")
        assert isinstance(normalized_stuff.content, ImageContent)
        assert normalized_stuff.content.url.startswith(PIPELEX_STORAGE_SCHEME)
        assert normalized_stuff.content.mime_type == "image/png"

        # Verify roundtrip: storage -> PreparedImage
        prompt_image = PromptImageFactory.make_prompt_image(uri=normalized_stuff.content.url)
        assert isinstance(prompt_image, PromptImageUri)

        prepared = await prepare_prompt_image(
            prompt_image=prompt_image,
            is_http_url_enabled=False,
        )

        assert isinstance(prepared, PreparedFileBase64)
        # Verify the data can be decoded and is non-empty
        decoded = base64.b64decode(prepared.base64_data)
        assert len(decoded) > 0

    @pytest.mark.usefixtures("mock_upload_local_content_disabled")
    async def test_user_image_local_file_passthrough_when_upload_disabled(self) -> None:
        """Test that local file paths are passed through when upload is disabled.

        When is_upload_local_content_enabled=False, local file paths should not be
        uploaded to storage. They should be passed through unchanged.
        """
        local_path = ImageTestCases.IMAGE_FILE_PATH_LOGO_TINY
        image_content = ImageContent(url=local_path)
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=image_content,
            name="local_image",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize (should not change local paths when upload is disabled)
        normalized_memory = await normalize_data_urls_to_storage(working_memory)

        # Verify URL was NOT changed
        normalized_stuff = normalized_memory.get_stuff("local_image")
        assert isinstance(normalized_stuff.content, ImageContent)
        assert normalized_stuff.content.url == local_path
