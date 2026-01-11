"""Unit tests for the with_images Jinja2 filter - validation and error handling.

Note: Core functionality tests using real Stuff classes are in integration tests:
- tests/integration/pipelex/pipes/llm_prompt_inputs/test_prompt_image_extraction.py
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from jinja2.runtime import Context, Undefined

from pipelex.cogt.templating.text_format import TextFormat
from pipelex.core.stuffs.jinja2_stuff_handlers import render_value_with_images
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_errors import Jinja2ContextError
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.jinja2_with_images_filter import with_images


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

        # Pass a list (which CAN contain images) to trigger the registry type check
        with pytest.raises(Jinja2ContextError, match="Expected ImageRegistry"):
            with_images(context, [])

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


class TestRenderValueWithImagesEdgeCases:
    """Edge case tests for render_value_with_images that don't need real Stuff classes."""

    def test_empty_list_returns_empty_string(self) -> None:
        """Test empty list returns empty string."""
        registry = ImageRegistry()

        result = render_value_with_images([], registry, TextFormat.PLAIN)

        assert result == ""
        assert len(registry.images) == 0

    def test_plain_string_value(self) -> None:
        """Test plain string value is rendered as-is."""
        registry = ImageRegistry()

        result = render_value_with_images("Hello World", registry, TextFormat.PLAIN)

        assert result == "Hello World"
