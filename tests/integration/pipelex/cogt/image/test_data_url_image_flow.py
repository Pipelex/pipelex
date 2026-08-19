"""Integration tests for data URL handling in the image flow."""

import base64
from typing import cast

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.image.prompt_image_utils import prepare_prompt_image
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.pipeline.input_normalizer import normalize_data_urls_to_storage
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.uri.prepared_file import PreparedFileBase64
from pipelex.urls import URLs
from tests.cases import ImageTestCases


class ArticleWithImage(StructuredContent):
    """Test StructuredContent with an embedded ImageContent."""

    title: str
    image: ImageContent
    description: str | None = None


class NestedArticle(StructuredContent):
    """Test StructuredContent with nested StructuredContent containing ImageContent."""

    main_article: ArticleWithImage
    related_image: ImageContent | None = None


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
        assert isinstance(prepared, PreparedFileBase64), f"Expected PreparedFileBase64 for {_topic}"
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
        normalized_memory = await normalize_data_urls_to_storage(working_memory, storage_scope="test/scope")

        # Verify the URL was converted to pipelex-storage://
        normalized_stuff = normalized_memory.get_stuff("test_image")
        assert isinstance(normalized_stuff.content, ImageContent)
        assert normalized_stuff.content.url.startswith("pipelex-storage://")

        # Verify the data is stored correctly and matches original
        stored_bytes = await provider.load(uri=normalized_stuff.content.url)
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
        normalized_memory = await normalize_data_urls_to_storage(working_memory, storage_scope="test/scope")
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
        assert isinstance(prepared, PreparedFileBase64)
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
        normalized_memory = await normalize_data_urls_to_storage(working_memory, storage_scope="test/scope")

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
        http_url = URLs.png_example_1
        image_content = ImageContent(url=http_url)
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE),
            content=image_content,
            name="test_image",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize
        normalized_memory = await normalize_data_urls_to_storage(working_memory, storage_scope="test/scope")

        # Verify URL was NOT changed
        normalized_stuff = normalized_memory.get_stuff("test_image")
        assert isinstance(normalized_stuff.content, ImageContent)
        assert normalized_stuff.content.url == http_url

    async def test_normalization_with_structured_content(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that normalizer handles StructuredContent with embedded ImageContent."""
        # Setup in-memory storage
        provider = InMemoryStorageProvider()
        mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=provider)

        # Create StructuredContent with embedded ImageContent containing data URL
        article = ArticleWithImage(
            title="Test Article",
            image=ImageContent(url=ImageTestCases.MINIMAL_PNG_DATA_URL),
            description="A test article with an image",
        )
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.DYNAMIC),
            content=article,
            name="test_article",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize
        normalized_memory = await normalize_data_urls_to_storage(working_memory, storage_scope="test/scope")

        # Verify the embedded image URL was converted to pipelex-storage://
        normalized_stuff = normalized_memory.get_stuff("test_article")
        assert isinstance(normalized_stuff.content, ArticleWithImage)
        normalized_article = normalized_stuff.content
        assert normalized_article.title == "Test Article"
        assert normalized_article.description == "A test article with an image"
        assert normalized_article.image.url.startswith("pipelex-storage://")

        # Verify the stored data is correct
        stored_bytes = await provider.load(uri=normalized_article.image.url)
        expected_bytes = base64.b64decode(ImageTestCases.MINIMAL_PNG_BASE64)
        assert stored_bytes == expected_bytes

    async def test_normalization_with_nested_structured_content(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that normalizer recursively handles nested StructuredContent."""
        # Setup in-memory storage
        provider = InMemoryStorageProvider()
        mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=provider)

        # Create nested StructuredContent with ImageContent at multiple levels
        nested = NestedArticle(
            main_article=ArticleWithImage(
                title="Main Article",
                image=ImageContent(url=ImageTestCases.MINIMAL_PNG_DATA_URL),
            ),
            related_image=ImageContent(url=ImageTestCases.MINIMAL_JPEG_DATA_URL),
        )
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.DYNAMIC),
            content=nested,
            name="nested_article",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize
        normalized_memory = await normalize_data_urls_to_storage(working_memory, storage_scope="test/scope")

        # Verify all image URLs were converted
        normalized_stuff = normalized_memory.get_stuff("nested_article")
        assert isinstance(normalized_stuff.content, NestedArticle)
        normalized_nested = normalized_stuff.content

        # Check nested ImageContent
        assert normalized_nested.main_article.image.url.startswith("pipelex-storage://")

        # Check top-level ImageContent
        assert normalized_nested.related_image is not None
        assert normalized_nested.related_image.url.startswith("pipelex-storage://")

        # Verify both stored data are correct
        nested_stored = await provider.load(uri=normalized_nested.main_article.image.url)
        assert nested_stored == base64.b64decode(ImageTestCases.MINIMAL_PNG_BASE64)

        related_stored = await provider.load(uri=normalized_nested.related_image.url)
        assert related_stored == base64.b64decode(ImageTestCases.MINIMAL_JPEG_BASE64)

    async def test_normalization_with_list_in_structured_content(
        self,
        mocker: MockerFixture,
    ) -> None:
        """Test that normalizer handles lists of ImageContent within StructuredContent."""
        # Setup in-memory storage
        provider = InMemoryStorageProvider()
        mocker.patch("pipelex.pipeline.input_normalizer.get_storage_provider", return_value=provider)

        # Create a StructuredContent subclass with a list of images
        class GalleryContent(StructuredContent):
            title: str
            images: list[ImageContent]

        gallery = GalleryContent(
            title="Test Gallery",
            images=[
                ImageContent(url=ImageTestCases.MINIMAL_PNG_DATA_URL),
                ImageContent(url=ImageTestCases.MINIMAL_JPEG_DATA_URL),
            ],
        )
        stuff = StuffFactory.make_stuff(
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.DYNAMIC),
            content=gallery,
            name="gallery",
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff=stuff)

        # Normalize
        normalized_memory = await normalize_data_urls_to_storage(working_memory, storage_scope="test/scope")

        # Verify all images in the list were converted
        normalized_stuff = normalized_memory.get_stuff("gallery")
        assert isinstance(normalized_stuff.content, GalleryContent)
        normalized_gallery = normalized_stuff.content
        assert len(normalized_gallery.images) == 2
        for image_item in normalized_gallery.images:
            assert image_item.url.startswith("pipelex-storage://")
