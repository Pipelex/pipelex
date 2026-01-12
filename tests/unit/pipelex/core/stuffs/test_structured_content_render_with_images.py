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


class TestStructuredContentRenderWithImages:
    """Tests for StructuredContent.render_with_images()."""

    def test_plain_list_of_image_content_extracts_images(self) -> None:
        """Test that plain list[ImageContent] fields have images extracted properly."""
        content = CustomStructuredWithPlainList(
            title="Test Document",
            images=[
                ImageContent(url="https://example.com/image1.png"),
                ImageContent(url="https://example.com/image2.png"),
                ImageContent(url="https://example.com/image3.png"),
            ],
        )
        registry = ImageRegistry()

        result = content.render_with_images(registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
        assert "[Image 2]" in result
        assert "[Image 3]" in result
        assert len(registry.images) == 3
        assert registry.images[0].url == "https://example.com/image1.png"
        assert registry.images[1].url == "https://example.com/image2.png"
        assert registry.images[2].url == "https://example.com/image3.png"

    def test_dict_with_image_content_values_extracts_images(self) -> None:
        """Test that dict with ImageContent values has images extracted properly."""
        content = CustomStructuredWithDict(
            title="Gallery",
            image_map={
                "cover": ImageContent(url="https://example.com/cover.png"),
                "background": ImageContent(url="https://example.com/bg.png"),
            },
        )
        registry = ImageRegistry()

        result = content.render_with_images(registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
        assert "[Image 2]" in result
        assert len(registry.images) == 2

    def test_nested_list_of_images_extracts_all(self) -> None:
        """Test that nested lists containing ImageContent have all images extracted."""
        content = CustomStructuredWithNestedList(
            title="Nested Gallery",
            image_groups=[
                [
                    ImageContent(url="https://example.com/g1-i1.png"),
                    ImageContent(url="https://example.com/g1-i2.png"),
                ],
                [
                    ImageContent(url="https://example.com/g2-i1.png"),
                ],
            ],
        )
        registry = ImageRegistry()

        result = content.render_with_images(registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
        assert "[Image 2]" in result
        assert "[Image 3]" in result
        assert len(registry.images) == 3

    def test_image_renderable_field_delegates_properly(self) -> None:
        """Test that ImageRenderable fields (like TextAndImagesContent) work correctly."""
        content = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Some document text"),
                images=[
                    ImageContent(url="https://example.com/page-image.png"),
                ],
            ),
            page_view=ImageContent(url="https://example.com/page-view.png"),
        )
        registry = ImageRegistry()

        result = content.render_with_images(registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
        assert "[Image 2]" in result
        assert "Some document text" in result
        assert len(registry.images) == 2

    def test_page_content_extracts_all_nested_images(self) -> None:
        """Test that PageContent properly extracts images from text_and_images and page_view."""
        page = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Page content"),
                images=[
                    ImageContent(url="https://example.com/embedded1.png"),
                    ImageContent(url="https://example.com/embedded2.png"),
                ],
            ),
            page_view=ImageContent(url="https://example.com/page-screenshot.png"),
        )
        registry = ImageRegistry()

        result = page.render_with_images(registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
        assert "[Image 2]" in result
        assert "[Image 3]" in result
        assert len(registry.images) == 3
        assert registry.images[0].url == "https://example.com/embedded1.png"
        assert registry.images[1].url == "https://example.com/embedded2.png"
        assert registry.images[2].url == "https://example.com/page-screenshot.png"

    def test_empty_list_produces_no_images(self) -> None:
        """Test that empty list fields don't cause issues."""
        content = CustomStructuredWithPlainList(
            title="Empty Gallery",
            images=[],
        )
        registry = ImageRegistry()

        result = content.render_with_images(registry, TextFormat.PLAIN)

        assert "title:" in result.lower()
        assert len(registry.images) == 0

    def test_none_page_view_handled_correctly(self) -> None:
        """Test that None optional fields are handled correctly."""
        page = PageContent(
            text_and_images=TextAndImagesContent(
                text=TextContent(text="Text only"),
                images=[ImageContent(url="https://example.com/single.png")],
            ),
            page_view=None,
        )
        registry = ImageRegistry()

        result = page.render_with_images(registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
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
            artefact.render_with_images(registry, TextFormat.PLAIN)
