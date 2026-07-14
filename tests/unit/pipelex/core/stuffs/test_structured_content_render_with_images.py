"""Unit tests for StructuredContent.render_with_images()."""

from pathlib import Path
from typing import Callable

import pytest

from pipelex.cogt.templating.text_format import TextFormat
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.stuff_artefact import StuffArtefact
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_native_concept
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.urls import URLs


class CustomStructuredWithPlainList(StructuredContent):
    """Test class with plain Python list of ImageContent."""

    title: str
    images: list[ImageContent]


class CustomStructuredWithDict(StructuredContent):
    """Test class with dict containing ImageContent values."""

    title: str
    image_map: dict[str, ImageContent]


class CustomStructuredWithNestedList(StructuredContent):
    """Test class with nested list structure."""

    title: str
    image_groups: list[list[ImageContent]]


class TestData:
    """Expected values for render_with_images tests."""

    EXPECTED_PLAIN_LIST = "title: Test Document\nimages: [Image 1]\n[Image 2]\n[Image 3]"
    EXPECTED_DICT = "title: Gallery\nimage_map: cover: [Image 1]\nbackground: [Image 2]"
    EXPECTED_NESTED_LIST = "title: Nested Gallery\nimage_groups: [Image 1]\n[Image 2]\n[Image 3]"
    EXPECTED_IMAGE_RENDERABLE = "text_and_images: Some document text\n[Image 1]\npage_view: [Image 2]"
    EXPECTED_PAGE_CONTENT_ALL = "text_and_images: Page content\n[Image 1]\n[Image 2]\npage_view: [Image 3]"
    EXPECTED_EMPTY_LIST = "title: Empty Gallery"
    EXPECTED_NONE_PAGE_VIEW = "text_and_images: Text only\n[Image 1]"


class TestStructuredContentRenderWithImages:
    """Tests for StructuredContent.render_with_images()."""

    def test_plain_list_of_image_content_extracts_images(self) -> None:
        """Test that plain list[ImageContent] fields have images extracted properly."""
        content = CustomStructuredWithPlainList(
            title="Test Document",
            images=[
                ImageContent(url=URLs.png_example_1),
                ImageContent(url=URLs.png_example_2),
                ImageContent(url=URLs.png_example_3),
            ],
        )
        registry = ImageRegistry()

        result = content.render_with_images(registry=registry, text_format=TextFormat.PLAIN)

        assert result == TestData.EXPECTED_PLAIN_LIST
        assert len(registry.images) == 3
        assert registry.images[0].url == URLs.png_example_1
        assert registry.images[1].url == URLs.png_example_2
        assert registry.images[2].url == URLs.png_example_3

    def test_dict_with_image_content_values_extracts_images(self) -> None:
        """Test that dict with ImageContent values has images extracted properly."""
        content = CustomStructuredWithDict(
            title="Gallery",
            image_map={
                "cover": ImageContent(url=URLs.png_example_1),
                "background": ImageContent(url=URLs.png_example_2),
            },
        )
        registry = ImageRegistry()

        result = content.render_with_images(registry=registry, text_format=TextFormat.PLAIN)

        assert result == TestData.EXPECTED_DICT
        assert len(registry.images) == 2

    def test_nested_list_of_images_extracts_all(self) -> None:
        """Test that nested lists containing ImageContent have all images extracted."""
        content = CustomStructuredWithNestedList(
            title="Nested Gallery",
            image_groups=[
                [
                    ImageContent(url=URLs.png_example_1),
                    ImageContent(url=URLs.png_example_2),
                ],
                [
                    ImageContent(url=URLs.png_example_3),
                ],
            ],
        )
        registry = ImageRegistry()

        result = content.render_with_images(registry=registry, text_format=TextFormat.PLAIN)

        assert result == TestData.EXPECTED_NESTED_LIST
        assert len(registry.images) == 3

    def test_image_renderable_field_delegates_properly(self) -> None:
        """Test that ImageRenderable fields (like TextAndImagesContent) work correctly."""
        content = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Some document text"),
                images=[
                    ImageContent(url=URLs.png_example_1),
                ],
            ),
            page_view=ImageContent(url=URLs.png_example_3),
        )
        registry = ImageRegistry()

        result = content.render_with_images(registry=registry, text_format=TextFormat.PLAIN)

        assert result == TestData.EXPECTED_IMAGE_RENDERABLE
        assert len(registry.images) == 2

    def test_page_content_extracts_all_nested_images(self) -> None:
        """Test that PageContent properly extracts images from text_and_images and page_view."""
        page = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Page content"),
                images=[
                    ImageContent(url=URLs.png_example_1),
                    ImageContent(url=URLs.png_example_2),
                ],
            ),
            page_view=ImageContent(url=URLs.png_example_3),
        )
        registry = ImageRegistry()

        result = page.render_with_images(registry=registry, text_format=TextFormat.PLAIN)

        assert result == TestData.EXPECTED_PAGE_CONTENT_ALL
        assert len(registry.images) == 3
        assert registry.images[0].url == URLs.png_example_1
        assert registry.images[1].url == URLs.png_example_2
        assert registry.images[2].url == URLs.png_example_3

    def test_empty_list_produces_no_images(self) -> None:
        """Test that empty list fields don't cause issues."""
        content = CustomStructuredWithPlainList(
            title="Empty Gallery",
            images=[],
        )
        registry = ImageRegistry()

        result = content.render_with_images(registry=registry, text_format=TextFormat.PLAIN)

        assert result == TestData.EXPECTED_EMPTY_LIST
        assert len(registry.images) == 0

    def test_none_page_view_handled_correctly(self) -> None:
        """Test that None optional fields are handled correctly."""
        page = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Text only"),
                images=[ImageContent(url=URLs.png_example_1)],
            ),
            page_view=None,
        )
        registry = ImageRegistry()

        result = page.render_with_images(registry=registry, text_format=TextFormat.PLAIN)

        assert result == TestData.EXPECTED_NONE_PAGE_VIEW
        assert len(registry.images) == 1


class TestStuffArtefactWithImagesFailFast:
    """Tests for fail-fast behavior when | with_images is used on non-image content."""

    def test_text_content_raises_type_error_via_artefact(self, load_test_library: Callable[[list[Path]], None]) -> None:
        """Test that TextContent wrapped in StuffArtefact raises TypeError."""
        load_test_library([Path("tests/integration/pipelex/pipes/pipelines")])

        stuff = StuffFactory.make_stuff(
            concept=get_native_concept(NativeConceptCode.TEXT),
            content=TextContent(text="Plain text without images"),
            name="text_stuff",
        )
        artefact = StuffArtefact(stuff)
        registry = ImageRegistry()

        with pytest.raises(TypeError, match="does not implement ImageRenderable"):
            artefact.render_with_images(registry=registry, text_format=TextFormat.PLAIN)
