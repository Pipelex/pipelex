"""Unit tests for the with_images Jinja2 filter - validation and error handling.

Note: Core functionality tests using real Stuff classes are in integration tests:
- tests/integration/pipelex/pipes/llm_prompt_inputs/test_prompt_image_extraction.py
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from jinja2.runtime import Context, Undefined

from pipelex.cogt.templating.text_format import TextFormat
from pipelex.tools.jinja2.exceptions import Jinja2ContextError
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.jinja2_with_images_filter import (
    _render_sequence_with_images,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
    with_images,
)


class TestWithImagesFilterValidation:
    """Tests for with_images filter error handling and edge cases."""

    def _make_context(self, registry: ImageRegistry | None = None, text_format: TextFormat = TextFormat.PLAIN) -> Context:
        """Create a mock Jinja2 context."""
        context_dict: dict[str, Any] = {}
        if registry is not None:
            context_dict[Jinja2ContextKey.IMAGE_REGISTRY] = registry
        context_dict[Jinja2ContextKey.TEXT_FORMAT] = text_format

        mock_env = MagicMock()
        mock_env.undefined = Undefined

        context = MagicMock(spec=Context)
        context.get = lambda key, default=None: context_dict.get(key, default)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
        context.environment = mock_env

        return context

    def test_with_images_raises_on_undefined(self) -> None:
        """Test with_images raises error for undefined value."""
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        with pytest.raises(Jinja2ContextError, match="undefined"):
            with_images(context, Undefined())

    def test_with_images_raises_on_wrong_registry_type(self) -> None:
        """Test with_images raises if registry is wrong type."""
        context_dict: dict[str, Any] = {
            Jinja2ContextKey.IMAGE_REGISTRY: "not_a_registry",
            Jinja2ContextKey.TEXT_FORMAT: TextFormat.PLAIN,
        }

        context = MagicMock(spec=Context)
        context.get = lambda key, default=None: context_dict.get(key, default)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

        # Pass a list (which is accepted by the filter) to trigger the registry type check
        with pytest.raises(Jinja2ContextError, match="Expected ImageRegistry"):
            with_images(context, [])

    def test_with_images_raises_on_string_input(self) -> None:
        """Test with_images raises error when receiving a plain string.

        This catches the common mistake of chaining filters in wrong order,
        e.g., {{ pages | tag | with_images }} where tag converts to string first.
        """
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        with pytest.raises(Jinja2ContextError, match="does not implement the ImageRenderable protocol"):
            with_images(context, "This is a plain string")

    def test_with_images_raises_on_number_input(self) -> None:
        """Test with_images raises error when receiving a number."""
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        with pytest.raises(Jinja2ContextError, match="does not implement the ImageRenderable protocol"):
            with_images(context, 42)

    def test_with_images_raises_on_dict_input(self) -> None:
        """Test with_images raises error when receiving a plain dict."""
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        with pytest.raises(Jinja2ContextError, match="does not implement the ImageRenderable protocol"):
            with_images(context, {"key": "value"})

    def test_with_images_accepts_empty_list(self) -> None:
        """Test with_images handles empty list gracefully."""
        registry = ImageRegistry()
        context = self._make_context(registry=registry)

        result = with_images(context, [])

        assert result == ""
        assert len(registry.images) == 0


class TestRenderSequenceWithImages:
    """Tests for _render_sequence_with_images helper function."""

    def test_empty_list_returns_empty_string(self) -> None:
        """Test empty list returns empty string."""
        registry = ImageRegistry()

        result = _render_sequence_with_images([], registry, TextFormat.PLAIN)

        assert result == ""
        assert len(registry.images) == 0

    def test_empty_tuple_returns_empty_string(self) -> None:
        """Test empty tuple returns empty string."""
        registry = ImageRegistry()

        result = _render_sequence_with_images((), registry, TextFormat.PLAIN)

        assert result == ""
        assert len(registry.images) == 0

    def test_non_image_renderable_items_converted_to_string(self) -> None:
        """Test that non-ImageRenderable items are converted to string."""
        registry = ImageRegistry()

        result = _render_sequence_with_images(["hello", 42, None], registry, TextFormat.PLAIN)

        # Items that convert to truthy strings are included
        assert "hello" in result
        assert "42" in result
        # None converts to "None" which is truthy
        assert "None" in result
