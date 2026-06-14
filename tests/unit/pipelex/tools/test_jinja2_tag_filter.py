"""Unit tests for the tag Jinja2 filter - validation and error handling.

Note: Core functionality tests using real Stuff classes are in integration tests.
"""

from typing import Any

import pytest
from jinja2.runtime import Context, Undefined
from pytest_mock import MockerFixture

from pipelex.cogt.templating.templating_style import TagStyle
from pipelex.tools.jinja2.exceptions import Jinja2ContextError
from pipelex.tools.jinja2.jinja2_filters import apply_tag_style, tag
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.tag_renderable import TagRenderable


@pytest.mark.asyncio(loop_scope="class")
class TestTagFilterValidation:
    """Tests for tag filter error handling and edge cases."""

    def _make_context(self, mocker: MockerFixture, tag_style: TagStyle = TagStyle.TICKS) -> Any:
        """Create a mock Jinja2 context."""
        context_dict: dict[str, Any] = {
            Jinja2ContextKey.TAG_STYLE: tag_style,
        }

        mock_env = mocker.MagicMock()
        mock_env.undefined = Undefined

        context = mocker.MagicMock(spec=Context)
        context.get = lambda key, default=None: context_dict.get(key, default)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
        context.environment = mock_env

        return context

    async def test_tag_raises_on_undefined(self, mocker: MockerFixture) -> None:
        """Test tag raises error for undefined value."""
        context = self._make_context(mocker)

        with pytest.raises(Jinja2ContextError, match="undefined"):
            await tag(context, value=Undefined())

    async def test_tag_raises_on_undefined_with_tag_name(self, mocker: MockerFixture) -> None:
        """Test tag raises error for undefined value with tag name in message."""
        context = self._make_context(mocker)

        with pytest.raises(Jinja2ContextError, match="tag_name 'my_tag'"):
            await tag(context, value=Undefined(), tag_name="my_tag")

    async def test_tag_with_string_converts_to_string(self, mocker: MockerFixture) -> None:
        """Test tag filter converts plain string input."""
        context = self._make_context(mocker)

        result = await tag(context, value="hello world")

        assert "hello world" in result
        assert "```" in result  # Default style is TICKS

    async def test_tag_with_number_converts_to_string(self, mocker: MockerFixture) -> None:
        """Test tag filter converts number input to string."""
        context = self._make_context(mocker)

        result = await tag(context, value=42)

        assert "42" in result

    async def test_tag_with_custom_name(self, mocker: MockerFixture) -> None:
        """Test tag filter uses provided custom tag name."""
        context = self._make_context(mocker, tag_style=TagStyle.XML)

        result = await tag(context, value="content", tag_name="custom")

        assert "<custom>" in result
        assert "</custom>" in result
        assert "content" in result

    async def test_tag_with_tag_renderable(self, mocker: MockerFixture) -> None:
        """Test tag filter uses TagRenderable protocol."""
        context = self._make_context(mocker)

        # Create a mock TagRenderable with async method
        mock_renderable = mocker.MagicMock(spec=TagRenderable)
        mock_renderable.render_for_tag_async = mocker.AsyncMock(return_value="rendered content")
        mock_renderable.default_tag_name = "my_stuff"

        result = await tag(context, value=mock_renderable)

        mock_renderable.render_for_tag_async.assert_called_once()
        assert "rendered content" in result
        assert "my_stuff" in result  # Uses default_tag_name

    async def test_tag_with_tag_renderable_custom_name_overrides(self, mocker: MockerFixture) -> None:
        """Test custom tag name overrides TagRenderable.default_tag_name."""
        context = self._make_context(mocker, tag_style=TagStyle.XML)

        mock_renderable = mocker.MagicMock(spec=TagRenderable)
        mock_renderable.render_for_tag_async = mocker.AsyncMock(return_value="content")
        mock_renderable.default_tag_name = "default_name"

        result = await tag(context, value=mock_renderable, tag_name="override_name")

        assert "<override_name>" in result
        assert "default_name" not in result


class TestApplyTagStyle:
    """Tests for apply_tag_style helper function."""

    def _make_context(self, mocker: MockerFixture, tag_style: TagStyle) -> Any:
        """Create a mock Jinja2 context with specific tag style."""
        context_dict: dict[str, Any] = {
            Jinja2ContextKey.TAG_STYLE: tag_style,
        }

        context = mocker.MagicMock(spec=Context)
        context.get = lambda key, default=None: context_dict.get(key, default)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

        return context

    def test_no_tag_style_returns_value_unchanged(self, mocker: MockerFixture) -> None:
        """Test NO_TAG style returns value unchanged."""
        context = self._make_context(mocker, TagStyle.NO_TAG)

        result = apply_tag_style(context, value="hello", tag_name="my_tag")

        assert result == "hello"

    def test_ticks_style_without_tag_name(self, mocker: MockerFixture) -> None:
        """Test TICKS style without tag name."""
        context = self._make_context(mocker, TagStyle.TICKS)

        result = apply_tag_style(context, value="content", tag_name=None)

        assert result == "```\ncontent\n```"

    def test_ticks_style_with_tag_name(self, mocker: MockerFixture) -> None:
        """Test TICKS style with tag name."""
        context = self._make_context(mocker, TagStyle.TICKS)

        result = apply_tag_style(context, value="content", tag_name="my_tag")

        assert result == "my_tag: ```\ncontent\n```"

    def test_xml_style_without_tag_name_uses_default(self, mocker: MockerFixture) -> None:
        """Test XML style uses 'data' as default tag name."""
        context = self._make_context(mocker, TagStyle.XML)

        result = apply_tag_style(context, value="content", tag_name=None)

        assert result == "<data>\ncontent\n</data>"

    def test_xml_style_with_tag_name(self, mocker: MockerFixture) -> None:
        """Test XML style with tag name."""
        context = self._make_context(mocker, TagStyle.XML)

        result = apply_tag_style(context, value="content", tag_name="my_tag")

        assert result == "<my_tag>\ncontent\n</my_tag>"

    def test_square_brackets_style_without_tag_name_uses_default(self, mocker: MockerFixture) -> None:
        """Test SQUARE_BRACKETS style uses 'data' as default tag name."""
        context = self._make_context(mocker, TagStyle.SQUARE_BRACKETS)

        result = apply_tag_style(context, value="content", tag_name=None)

        assert result == "[data]\ncontent\n[/data]"

    def test_square_brackets_style_with_tag_name(self, mocker: MockerFixture) -> None:
        """Test SQUARE_BRACKETS style with tag name."""
        context = self._make_context(mocker, TagStyle.SQUARE_BRACKETS)

        result = apply_tag_style(context, value="content", tag_name="my_tag")

        assert result == "[my_tag]\ncontent\n[/my_tag]"

    def test_default_style_is_ticks_when_not_set(self, mocker: MockerFixture) -> None:
        """Test default tag style is TICKS when not set in context."""
        context_dict: dict[str, Any] = {}  # No TAG_STYLE set

        context = mocker.MagicMock(spec=Context)
        context.get = lambda key, default=None: context_dict.get(key, default)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

        result = apply_tag_style(context, value="content", tag_name=None)

        assert "```" in result  # TICKS is default
