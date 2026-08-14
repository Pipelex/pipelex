"""Every styling filter fails loudly when the render context carries no templating style.

There used to be three independent fallbacks — `TagStyle.TICKS` in `apply_tag_style`, `TextFormat.PLAIN`
in the `format` filter and again in `with_images`. Each quietly decided the shape of a prompt nobody had
chosen a style for. Now that every prompt-rendering entry point resolves one, a missing key is a wiring
bug, and these tests are what keeps a convenience default from creeping back in.
"""

from typing import Any

import pytest
from jinja2.runtime import Context
from pytest_mock import MockerFixture

from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.jinja2.exceptions import Jinja2ContextError
from pipelex.tools.jinja2.image_registry import ImageRegistry
from pipelex.tools.jinja2.jinja2_filters import apply_tag_style, text_format
from pipelex.tools.jinja2.jinja2_models import Jinja2ContextKey
from pipelex.tools.jinja2.jinja2_with_images_filter import with_images


class TestStyleContextStrictness:
    def _make_context(self, mocker: MockerFixture, *, context_dict: dict[str, Any]) -> Any:
        context = mocker.MagicMock(spec=Context)
        context.get = lambda key, default=None: context_dict.get(key, default)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]
        return context

    def test_tag_style_missing_raises(self, mocker: MockerFixture) -> None:
        context = self._make_context(mocker, context_dict={})

        with pytest.raises(Jinja2ContextError, match="No templating style in the render context"):
            apply_tag_style(context=context, value="content", tag_name=None)

    @pytest.mark.asyncio
    async def test_text_format_missing_raises(self, mocker: MockerFixture) -> None:
        context = self._make_context(mocker, context_dict={})

        with pytest.raises(Jinja2ContextError, match="No templating style in the render context"):
            await text_format(context, value=TextContent(text="content"))

    def test_with_images_text_format_missing_raises(self, mocker: MockerFixture) -> None:
        context = self._make_context(mocker, context_dict={Jinja2ContextKey.IMAGE_REGISTRY: ImageRegistry()})

        with pytest.raises(Jinja2ContextError, match="No templating style in the render context"):
            with_images(context, TextContent(text="content"))

    @pytest.mark.asyncio
    async def test_an_explicit_filter_argument_still_bypasses_the_context(self, mocker: MockerFixture) -> None:
        """`{{ x | format("markdown") }}` names its own format, so it never reads the context key.

        Strictness is about the *absent* decision, not about forbidding a per-call one — pinned here so
        the raise above is not mistaken for "the context key is always required".
        """
        context = self._make_context(mocker, context_dict={})

        assert await text_format(context, value="plain string", text_format="markdown") == "plain string"
