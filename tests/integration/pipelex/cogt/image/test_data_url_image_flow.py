"""Integration tests for data URL handling in the image flow."""

import base64
from typing import cast

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.image.prepared_image import PreparedImageBase64
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.image.prompt_image_utils import prepare_prompt_image
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipeline.input_normalizer import normalize_data_urls_to_storage
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from tests.cases import ImageTestCases


@pytest.mark.dry_runnable
@pytest.mark.asyncio(loop_scope="class")
class TestDataUrlImageFlow:
    """Integration tests for data URL handling in image flows."""

    @pytest.mark.parametrize(("_topic", "data_url"), ImageTestCases.DATA_URL_TEST_CASES)
    async def test_image_content_with_data_url_to_prompt_image(self, _topic: str, data_url: str) -> None:
        """Test that ImageContent with data URL converts correctly to PromptImage -> PreparedImage."""
        # Create ImageContent with data URL
        image_content = ImageContent(url=data_url)

        # Convert to PromptImage (as done in llm_prompt_blueprint.py)
        prompt_image = PromptImageFactory.make_prompt_image(uri=image_content.url)

        # Prepare for LLM API consumption
        prepared = await prepare_prompt_image(
            prompt_image=prompt_image,
            is_http_url_enabled=False,
        )

        # Verify result
        assert isinstance(prepared, PreparedImageBase64), f"Expected PreparedImageBase64 for {_topic}"
        # Verify base64 data can be decoded (valid format)
        decoded_bytes = base64.b64decode(prepared.base64_data)
        assert len(decoded_bytes) > 0

    @pytest.mark.parametrize(("_topic", "data_url"), ImageTestCases.DATA_URL_TEST_CASES)
    async def test_data_url_normalization_to_storage(
        self,
        mocker: MockerFixture,
        _topic: str,
        data_url: str,
    ) -> None:
        """Test that the normalizer converts data URLs to storage URIs."""
        # Setup in-memory storage
        provider = InMemoryStorageProvider()
        mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=provider)

        # Create ImageContent with data URL
        image_content = ImageContent(url=data_url)
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=image_content,
            name="test_image",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize
        normalized_memory = normalize_data_urls_to_storage(working_memory)

        # Verify the URL was converted to pipelex-storage://
        normalized_stuff = normalized_memory.get_stuff("test_image")
        assert isinstance(normalized_stuff.content, ImageContent)
        assert normalized_stuff.content.url.startswith("pipelex-storage://")

        # Verify the data is stored correctly and matches original
        stored_bytes = provider.load(uri=normalized_stuff.content.url)
        # Extract base64 data from the data URL for comparison
        base64_data = data_url.split(",", 1)[1]
        expected_bytes = base64.b64decode(base64_data)
        assert stored_bytes == expected_bytes

    @pytest.mark.parametrize(("_topic", "data_url"), ImageTestCases.DATA_URL_TEST_CASES)
    async def test_data_url_round_trip(
        self,
        mocker: MockerFixture,
        _topic: str,
        data_url: str,
    ) -> None:
        """Test full flow: data URL -> storage -> prepared image (verifies bytes match)."""
        # Setup in-memory storage
        provider = InMemoryStorageProvider()
        mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=provider)
        mocker.patch("pipelex.cogt.image.prompt_image_utils.get_storage_provider", return_value=provider)

        # Create ImageContent with data URL
        image_content = ImageContent(url=data_url)
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=image_content,
            name="test_image",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize to storage
        normalized_memory = normalize_data_urls_to_storage(working_memory)
        normalized_stuff = normalized_memory.get_stuff("test_image")
        assert isinstance(normalized_stuff.content, ImageContent)
        storage_uri = normalized_stuff.content.url

        # Convert back through PromptImage -> PreparedImage
        prompt_image = PromptImageFactory.make_prompt_image(uri=storage_uri)
        prepared = await prepare_prompt_image(
            prompt_image=prompt_image,
            is_http_url_enabled=False,
        )

        # Verify the round-trip preserves the data
        assert isinstance(prepared, PreparedImageBase64)
        # Extract original base64 for comparison
        original_base64 = data_url.split(",", 1)[1]
        assert prepared.base64_data == original_base64

    async def test_normalization_with_list_of_images(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that normalizer handles ListContent of ImageContent."""
        # Setup in-memory storage
        provider = InMemoryStorageProvider()
        mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=provider)

        # Create ListContent with multiple ImageContent items using shared test data
        image_contents = [
            ImageContent(url=ImageTestCases.MINIMAL_PNG_DATA_URL),
            ImageContent(url=ImageTestCases.MINIMAL_JPEG_DATA_URL),
        ]
        list_content = ListContent[ImageContent](items=image_contents)
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=list_content,
            name="image_list",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize
        normalized_memory = normalize_data_urls_to_storage(working_memory)

        # Verify all images were converted
        normalized_stuff = normalized_memory.get_stuff("image_list")
        normalized_content = normalized_stuff.content
        assert isinstance(normalized_content, ListContent)
        typed_list_content = cast("ListContent[ImageContent]", normalized_content)
        for image_item in typed_list_content.items:
            assert isinstance(image_item, ImageContent)
            assert image_item.url.startswith("pipelex-storage://")

    async def test_normalization_skips_non_data_urls(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that normalizer skips URLs that are not data URLs."""
        # Setup in-memory storage
        provider = InMemoryStorageProvider()
        mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=provider)

        # Create ImageContent with HTTP URL
        http_url = "https://example.com/image.png"
        image_content = ImageContent(url=http_url)
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=image_content,
            name="test_image",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize
        normalized_memory = normalize_data_urls_to_storage(working_memory)

        # Verify URL was NOT changed
        normalized_stuff = normalized_memory.get_stuff("test_image")
        assert isinstance(normalized_stuff.content, ImageContent)
        assert normalized_stuff.content.url == http_url
