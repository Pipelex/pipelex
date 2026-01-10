"""Tests for the with_images Jinja2 filter."""

from typing import Any, ClassVar
from unittest.mock import MagicMock

import pytest
from jinja2.runtime import Context, Undefined

from pipelex.cogt.templating.templating_style import TextFormat
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_errors import Jinja2ContextError
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.jinja2_with_images_filter import (
    _is_image_content,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    _is_list_content,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    _is_stuff_artefact,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    _is_stuff_content,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    _render_value_with_images,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    with_images,
)


class ImageContent:
    """Mock ImageContent class for testing - matches duck typing check."""

    def __init__(self, url: str) -> None:
        self.url = url


class ListContent:
    """Mock ListContent class for testing - matches duck typing check."""

    def __init__(self, items: list[Any]) -> None:
        self.items = items


class MockStuffContent:
    """Mock StuffContent for testing - must have model_fields."""

    model_fields: ClassVar[dict[str, Any]] = {}

    def rendered_str(self, _text_format: TextFormat) -> str:
        return "mock_rendered"


class PersonWithPhoto(MockStuffContent):
    """Struct with a single image field."""

    model_fields: ClassVar[dict[str, Any]] = {"name": ..., "photo": ...}

    def __init__(self, name: str, photo: ImageContent | None) -> None:
        self.name = name
        self.photo = photo


class ArticleWithImages(MockStuffContent):
    """Struct with multiple image fields."""

    model_fields: ClassVar[dict[str, Any]] = {"title": ..., "cover": ..., "thumbnail": ...}

    def __init__(self, title: str, cover: ImageContent | None, thumbnail: ImageContent | None) -> None:
        self.title = title
        self.cover = cover
        self.thumbnail = thumbnail


class NestedStruct(MockStuffContent):
    """Struct with nested struct containing image."""

    model_fields: ClassVar[dict[str, Any]] = {"label": ..., "inner": ...}

    def __init__(self, label: str, inner: MockStuffContent | None) -> None:
        self.label = label
        self.inner = inner


class StuffArtefact:
    """Mock StuffArtefact class for testing - matches duck typing check."""

    def __init__(self, root_dict: dict[str, Any]) -> None:
        self.root = root_dict

    def get(self, key: str, default: Any = None) -> Any:
        return self.root.get(key, default)


class TestDuckTypingChecks:
    """Tests for duck typing helper functions."""

    def test_is_image_content_with_image(self) -> None:
        """Test _is_image_content returns True for ImageContent."""
        img = ImageContent(url="http://example.com/image.png")
        assert _is_image_content(img) is True

    def test_is_image_content_with_non_image(self) -> None:
        """Test _is_image_content returns False for non-ImageContent."""
        assert _is_image_content("string") is False
        assert _is_image_content(123) is False
        assert _is_image_content({"url": "test"}) is False  # dict has url but wrong class name

    def test_is_list_content_with_list_content(self) -> None:
        """Test _is_list_content returns True for ListContent."""
        lst = ListContent(items=[])
        assert _is_list_content(lst) is True

    def test_is_list_content_with_regular_list(self) -> None:
        """Test _is_list_content returns False for regular list."""
        assert _is_list_content([1, 2, 3]) is False

    def test_is_stuff_content_with_stuff(self) -> None:
        """Test _is_stuff_content returns True for StuffContent."""
        stuff = PersonWithPhoto(name="Test", photo=None)
        assert _is_stuff_content(stuff) is True

    def test_is_stuff_content_excludes_image_content(self) -> None:
        """Test _is_stuff_content returns False for ImageContent."""
        img = ImageContent(url="http://example.com/image.png")
        assert _is_stuff_content(img) is False

    def test_is_stuff_content_excludes_stuff_artefact(self) -> None:
        """Test _is_stuff_content returns False for StuffArtefact."""
        artefact = StuffArtefact(root_dict={"_content": PersonWithPhoto(name="Test", photo=None)})
        assert _is_stuff_content(artefact) is False

    def test_is_stuff_artefact_with_valid_artefact(self) -> None:
        """Test _is_stuff_artefact returns True for StuffArtefact."""
        artefact = StuffArtefact(root_dict={"_content": "mock_content"})
        assert _is_stuff_artefact(artefact) is True

    def test_is_stuff_artefact_with_non_artefact(self) -> None:
        """Test _is_stuff_artefact returns False for non-StuffArtefact."""
        assert _is_stuff_artefact("string") is False
        assert _is_stuff_artefact({"_content": "value"}) is False  # dict has _content but wrong class
        assert _is_stuff_artefact(PersonWithPhoto(name="Test", photo=None)) is False

    def test_is_stuff_artefact_without_content_key(self) -> None:
        """Test _is_stuff_artefact returns False when _content key is missing."""
        artefact = StuffArtefact(root_dict={"other_key": "value"})
        assert _is_stuff_artefact(artefact) is False


class TestRenderValueWithImages:
    """Tests for _render_value_with_images function."""

    def test_image_content_returns_token(self) -> None:
        """Test ImageContent renders as [Image N] token."""
        registry = ImageRegistry()
        img = ImageContent(url="http://example.com/test.png")

        result = _render_value_with_images(img, registry, TextFormat.PLAIN)

        assert result == "[Image 1]"
        assert len(registry.images) == 1

    def test_second_image_gets_number_2(self) -> None:
        """Test second image gets [Image 2] token."""
        registry = ImageRegistry()
        img1 = ImageContent(url="http://example.com/first.png")
        img2 = ImageContent(url="http://example.com/second.png")

        _render_value_with_images(img1, registry, TextFormat.PLAIN)
        result2 = _render_value_with_images(img2, registry, TextFormat.PLAIN)

        assert result2 == "[Image 2]"
        assert len(registry.images) == 2

    def test_struct_with_single_image_field(self) -> None:
        """Test struct with single image field renders correctly."""
        registry = ImageRegistry()
        person = PersonWithPhoto(
            name="Alice",
            photo=ImageContent(url="http://example.com/alice.png"),
        )

        result = _render_value_with_images(person, registry, TextFormat.PLAIN)

        assert "photo: [Image 1]" in result
        assert "name: Alice" in result
        assert len(registry.images) == 1

    def test_struct_with_multiple_image_fields(self) -> None:
        """Test struct with multiple image fields renders all."""
        registry = ImageRegistry()
        article = ArticleWithImages(
            title="Test Article",
            cover=ImageContent(url="http://example.com/cover.png"),
            thumbnail=ImageContent(url="http://example.com/thumb.png"),
        )

        result = _render_value_with_images(article, registry, TextFormat.PLAIN)

        assert "cover: [Image 1]" in result
        assert "thumbnail: [Image 2]" in result
        assert len(registry.images) == 2

    def test_struct_with_none_image_field_skipped(self) -> None:
        """Test struct with None image field skips it."""
        registry = ImageRegistry()
        person = PersonWithPhoto(name="Bob", photo=None)

        result = _render_value_with_images(person, registry, TextFormat.PLAIN)

        assert "photo" not in result
        assert "name: Bob" in result
        assert len(registry.images) == 0

    def test_list_of_images_returns_tokens(self) -> None:
        """Test list of ImageContent renders each as token."""
        registry = ImageRegistry()
        images = [
            ImageContent(url="http://example.com/a.png"),
            ImageContent(url="http://example.com/b.png"),
            ImageContent(url="http://example.com/c.png"),
        ]

        result = _render_value_with_images(images, registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
        assert "[Image 2]" in result
        assert "[Image 3]" in result
        assert len(registry.images) == 3

    def test_list_content_of_images(self) -> None:
        """Test ListContent containing images."""
        registry = ImageRegistry()
        lst = ListContent(
            items=[
                ImageContent(url="http://example.com/1.png"),
                ImageContent(url="http://example.com/2.png"),
            ]
        )

        result = _render_value_with_images(lst, registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
        assert "[Image 2]" in result
        assert len(registry.images) == 2

    def test_list_of_structs_with_images(self) -> None:
        """Test list of structs where each has an image."""
        registry = ImageRegistry()
        people = [
            PersonWithPhoto(name="A", photo=ImageContent(url="http://example.com/a.png")),
            PersonWithPhoto(name="B", photo=ImageContent(url="http://example.com/b.png")),
        ]

        result = _render_value_with_images(people, registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
        assert "[Image 2]" in result
        assert len(registry.images) == 2

    def test_empty_list_returns_empty_string(self) -> None:
        """Test empty list returns empty string."""
        registry = ImageRegistry()

        result = _render_value_with_images([], registry, TextFormat.PLAIN)

        assert result == ""
        assert len(registry.images) == 0

    def test_tokens_numbered_sequentially_across_calls(self) -> None:
        """Test tokens are numbered sequentially even across separate calls."""
        registry = ImageRegistry()

        result1 = _render_value_with_images(
            ImageContent(url="http://example.com/1.png"),
            registry,
            TextFormat.PLAIN,
        )
        result2 = _render_value_with_images(
            [ImageContent(url="http://example.com/2.png"), ImageContent(url="http://example.com/3.png")],
            registry,
            TextFormat.PLAIN,
        )

        assert result1 == "[Image 1]"
        assert "[Image 2]" in result2
        assert "[Image 3]" in result2

    def test_deeply_nested_images(self) -> None:
        """Test images in deeply nested structures are found."""
        registry = ImageRegistry()
        inner = PersonWithPhoto(name="Nested", photo=ImageContent(url="http://example.com/nested.png"))
        outer = NestedStruct(label="Outer", inner=inner)

        result = _render_value_with_images(outer, registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
        assert len(registry.images) == 1

    def test_struct_without_images_renders_text(self) -> None:
        """Test struct without images renders field values as text."""
        registry = ImageRegistry()
        person = PersonWithPhoto(name="NoPhoto", photo=None)

        result = _render_value_with_images(person, registry, TextFormat.PLAIN)

        assert "name: NoPhoto" in result
        assert "[Image" not in result

    def test_plain_string_value(self) -> None:
        """Test plain string value is rendered as-is."""
        registry = ImageRegistry()

        result = _render_value_with_images("Hello World", registry, TextFormat.PLAIN)

        assert result == "Hello World"

    def test_stuff_artefact_extracts_content_images(self) -> None:
        """Test StuffArtefact extracts images from its _content field."""
        registry = ImageRegistry()
        # Create a mock content with an image
        inner_content = PersonWithPhoto(
            name="Alice",
            photo=ImageContent(url="http://example.com/alice.png"),
        )
        artefact = StuffArtefact(root_dict={"_content": inner_content})

        result = _render_value_with_images(artefact, registry, TextFormat.PLAIN)

        assert "[Image 1]" in result
        assert len(registry.images) == 1


class TestWithImagesFilter:
    """Tests for the with_images Jinja2 filter function."""

    def _make_context(self, registry: ImageRegistry | None = None, text_format: TextFormat = TextFormat.PLAIN) -> Context:
        """Create a mock Jinja2 context."""
        context_dict: dict[str, Any] = {}
        if registry is not None:
            context_dict[Jinja2ContextKey.IMAGE_REGISTRY] = registry
        context_dict[Jinja2ContextKey.TEXT_FORMAT] = text_format

        # Create a mock environment
        mock_env = MagicMock()
        mock_env.undefined = Undefined

        context = MagicMock(spec=Context)
        context.get = lambda key, default=None: context_dict.get(key, default)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
        context.environment = mock_env

        return context

    def test_with_images_returns_token_for_image(self) -> None:
        """Test with_images filter returns token for ImageContent."""
        registry = ImageRegistry()
        context = self._make_context(registry=registry)
        img = ImageContent(url="http://example.com/test.png")

        result = with_images(context, img)

        assert result == "[Image 1]"
        assert len(registry.images) == 1

    def test_with_images_creates_registry_if_missing(self) -> None:
        """Test with_images creates temporary registry if not in context."""
        context = self._make_context(registry=None)
        img = ImageContent(url="http://example.com/test.png")

        # Should not raise, creates temporary registry
        result = with_images(context, img)

        assert result == "[Image 1]"

    def test_with_images_raises_on_undefined(self) -> None:
        """Test with_images raises error for undefined value."""
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        with pytest.raises(Jinja2ContextError, match="undefined"):
            with_images(context, Undefined())

    def test_with_images_raises_on_wrong_registry_type(self) -> None:
        """Test with_images raises if registry is wrong type."""
        context_dict: dict[str, Any] = {Jinja2ContextKey.IMAGE_REGISTRY: "not_a_registry"}

        context = MagicMock(spec=Context)
        context.get = lambda key, default=None: context_dict.get(key, default)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

        with pytest.raises(Jinja2ContextError, match="Expected ImageRegistry"):
            with_images(context, ImageContent(url="test"))

    def test_with_images_uses_shared_registry(self) -> None:
        """Test multiple with_images calls share the same registry."""
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        result1 = with_images(context, ImageContent(url="http://example.com/1.png"))
        result2 = with_images(context, ImageContent(url="http://example.com/2.png"))

        assert result1 == "[Image 1]"
        assert result2 == "[Image 2]"
        assert len(registry.images) == 2

    def test_with_images_processes_struct(self) -> None:
        """Test with_images processes struct with nested images."""
        registry = ImageRegistry()
        context = self._make_context(registry=registry)
        person = PersonWithPhoto(
            name="Test",
            photo=ImageContent(url="http://example.com/photo.png"),
        )

        result = with_images(context, person)

        assert "photo: [Image 1]" in result
        assert len(registry.images) == 1

    def test_with_images_returns_string_type(self) -> None:
        """Test that with_images always returns a string, not a structured object.

        This is critical: because with_images returns a plain string, it must come
        LAST in any filter chain. Subsequent filters expecting structured data
        would receive a string instead and fail.
        """
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        # Test with image
        img_result = with_images(context, ImageContent(url="http://example.com/test.png"))
        assert isinstance(img_result, str)

        # Test with struct
        struct_result = with_images(context, PersonWithPhoto(name="Test", photo=None))
        assert isinstance(struct_result, str)

        # Test with list
        list_result = with_images(context, [ImageContent(url="http://example.com/1.png")])
        assert isinstance(list_result, str)

    def test_with_images_raises_on_string_input(self) -> None:
        """Test with_images raises error when receiving a plain string.

        This catches the common mistake of chaining filters in wrong order,
        e.g., {{ pages | tag | with_images }} where tag converts to string first.
        """
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        with pytest.raises(Jinja2ContextError, match="cannot contain images"):
            with_images(context, "This is a plain string")

    def test_with_images_raises_on_number_input(self) -> None:
        """Test with_images raises error when receiving a number."""
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        with pytest.raises(Jinja2ContextError, match="cannot contain images"):
            with_images(context, 42)

    def test_with_images_raises_on_dict_input(self) -> None:
        """Test with_images raises error when receiving a plain dict."""
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        with pytest.raises(Jinja2ContextError, match="cannot contain images"):
            with_images(context, {"key": "value"})
