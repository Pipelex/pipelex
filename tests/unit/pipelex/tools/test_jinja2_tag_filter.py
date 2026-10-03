"""Unit tests for the tag Jinja2 filter - validation and error handling.

Note: Core functionality tests using real Stuff classes are in integration tests.
"""

from typing import Any

import pytest
from jinja2.runtime import Context, Undefined
from pytest_mock import MockerFixture

from pipelex.tools.jinja2.exceptions import Jinja2ContextError
from pipelex.tools.jinja2.jinja2_filters import apply_tag_style, tag
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.templating.templating_style import TagStyle


class _TagRenderableStub:
    """Implements TagRenderable in its class: the tag filter never calls a rendering method an instance merely holds."""

    def __init__(self, *, rendered: str, default_tag_name: str) -> None:
        self.rendered = rendered
        self.name = default_tag_name
        self.render_calls = 0

    async def render_for_tag_async(self) -> str:
        self.render_calls += 1
        return self.rendered

    @property
    def default_tag_name(self) -> str:
        return self.name


@pytest.mark.asyncio(loop_scope="class")
class TestTagFilterValidation:
    """Tests for tag filter error handling and edge cases."""

    def _make_context(self, mocker: MockerFixture, *, tag_style: TagStyle) -> Any:
        """Create a mock Jinja2 context. The style is explicit: no filter supplies one any more."""
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
        context = self._make_context(mocker, tag_style=TagStyle.TICKS)

        with pytest.raises(Jinja2ContextError, match="undefined"):
            await tag(context, value=Undefined())

    async def test_tag_raises_on_undefined_with_tag_name(self, mocker: MockerFixture) -> None:
        """Test tag raises error for undefined value with tag name in message."""
        context = self._make_context(mocker, tag_style=TagStyle.TICKS)

        with pytest.raises(Jinja2ContextError, match="tag_name 'my_tag'"):
            await tag(context, value=Undefined(), tag_name="my_tag")

    async def test_tag_with_string_converts_to_string(self, mocker: MockerFixture) -> None:
        """Test tag filter converts plain string input."""
        context = self._make_context(mocker, tag_style=TagStyle.TICKS)

        result = await tag(context, value="hello world")

        assert "hello world" in result
        assert "```" in result

    async def test_tag_with_number_converts_to_string(self, mocker: MockerFixture) -> None:
        """Test tag filter converts number input to string."""
        context = self._make_context(mocker, tag_style=TagStyle.TICKS)

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
        context = self._make_context(mocker, tag_style=TagStyle.TICKS)
        renderable = _TagRenderableStub(rendered="rendered content", default_tag_name="my_stuff")

        result = await tag(context, value=renderable)

        assert renderable.render_calls == 1
        assert "rendered content" in result
        assert "my_stuff" in result  # Uses default_tag_name

    async def test_tag_with_tag_renderable_custom_name_overrides(self, mocker: MockerFixture) -> None:
        """Test custom tag name overrides TagRenderable.default_tag_name."""
        context = self._make_context(mocker, tag_style=TagStyle.XML)

        renderable = _TagRenderableStub(rendered="content", default_tag_name="default_name")

        result = await tag(context, value=renderable, tag_name="override_name")

        assert renderable.render_calls == 1
        assert "<override_name>" in result
        assert "default_name" not in result


class TestApplyTagStyle:
    """Tests for apply_tag_style helper function."""

    def _make_context(self, mocker: MockerFixture, *, tag_style: TagStyle) -> Any:
        """Create a mock Jinja2 context with specific tag style."""
        context_dict: dict[str, Any] = {
            Jinja2ContextKey.TAG_STYLE: tag_style,
        }

        context = mocker.MagicMock(spec=Context)
        context.get = lambda key, default=None: context_dict.get(key, default)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

        return context

    def test_no_tag_style_returns_value_unchanged(self, mocker: MockerFixture) -> None:
        """Test NO_TAG style returns value unchanged."""
        context = self._make_context(mocker, tag_style=TagStyle.NO_TAG)

        result = apply_tag_style(context=context, value="hello", tag_name="my_tag")

        assert result == "hello"

    def test_ticks_style_without_tag_name(self, mocker: MockerFixture) -> None:
        """Test TICKS style without tag name."""
        context = self._make_context(mocker, tag_style=TagStyle.TICKS)

        result = apply_tag_style(context=context, value="content", tag_name=None)

        assert result == "```\ncontent\n```"

    def test_ticks_style_with_tag_name(self, mocker: MockerFixture) -> None:
        """Test TICKS style with tag name."""
        context = self._make_context(mocker, tag_style=TagStyle.TICKS)

        result = apply_tag_style(context=context, value="content", tag_name="my_tag")

        assert result == "my_tag: ```\ncontent\n```"

    def test_xml_style_without_tag_name_uses_default(self, mocker: MockerFixture) -> None:
        """Test XML style uses 'data' as default tag name."""
        context = self._make_context(mocker, tag_style=TagStyle.XML)

        result = apply_tag_style(context=context, value="content", tag_name=None)

        assert result == "<data>\ncontent\n</data>"

    def test_xml_style_with_tag_name(self, mocker: MockerFixture) -> None:
        """Test XML style with tag name."""
        context = self._make_context(mocker, tag_style=TagStyle.XML)

        result = apply_tag_style(context=context, value="content", tag_name="my_tag")

        assert result == "<my_tag>\ncontent\n</my_tag>"

    def test_square_brackets_style_without_tag_name_uses_default(self, mocker: MockerFixture) -> None:
        """Test SQUARE_BRACKETS style uses 'data' as default tag name."""
        context = self._make_context(mocker, tag_style=TagStyle.SQUARE_BRACKETS)

        result = apply_tag_style(context=context, value="content", tag_name=None)

        assert result == "[data]\ncontent\n[/data]"

    def test_square_brackets_style_with_tag_name(self, mocker: MockerFixture) -> None:
        """Test SQUARE_BRACKETS style with tag name."""
        context = self._make_context(mocker, tag_style=TagStyle.SQUARE_BRACKETS)

        result = apply_tag_style(context=context, value="content", tag_name="my_tag")

        assert result == "[my_tag]\ncontent\n[/my_tag]"

    def test_missing_tag_style_raises(self, mocker: MockerFixture) -> None:
        """A style-less render context is an error, not a silent triple-backtick default.

        Every prompt-rendering entry point resolves a templating style, so a missing TAG_STYLE means
        the render was set up without one — which used to reshape the prompt quietly.
        """
        context_dict: dict[str, Any] = {}  # No TAG_STYLE set

        context = mocker.MagicMock(spec=Context)
        context.get = lambda key, default=None: context_dict.get(key, default)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

        with pytest.raises(Jinja2ContextError, match="No templating style in the render context"):
            apply_tag_style(context=context, value="content", tag_name=None)
