"""Unit tests for Jinja2 environment filter registration.

Verifies that async filters are excluded from sync environments to prevent
silent corruption (coroutine objects rendered as strings instead of actual content).
"""

import pytest

from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_filters import tag as async_tag_filter
from pipelex.tools.jinja2.jinja2_filters import text_format as async_text_format_filter
from pipelex.tools.jinja2.jinja2_models import Jinja2FilterName
from pipelex.tools.jinja2.template_category import TemplateCategory

CATEGORIES_WITH_ASYNC_FILTERS = [
    TemplateCategory.BASIC,
    TemplateCategory.HTML,
    TemplateCategory.MARKDOWN,
    TemplateCategory.LLM_PROMPT,
    TemplateCategory.IMG_GEN_PROMPT,
]


class TestJinja2EnvironmentFilterRegistration:
    """Tests that async filters are excluded from sync Jinja2 environments."""

    @pytest.mark.parametrize("template_category", CATEGORIES_WITH_ASYNC_FILTERS)
    def test_async_filters_registered_when_async_enabled(self, template_category: TemplateCategory) -> None:
        """All category filters should be registered when enable_async is True."""
        jinja2_env = make_jinja2_env_without_loader(
            template_category=template_category,
            enable_async=True,
        )
        assert jinja2_env.filters[Jinja2FilterName.TAG] is async_tag_filter
        assert jinja2_env.filters[Jinja2FilterName.FORMAT] is async_text_format_filter

    @pytest.mark.parametrize("template_category", CATEGORIES_WITH_ASYNC_FILTERS)
    def test_async_filters_excluded_when_async_disabled(self, template_category: TemplateCategory) -> None:
        """Async filters (tag, text_format) should NOT be registered when enable_async is False."""
        jinja2_env = make_jinja2_env_without_loader(
            template_category=template_category,
            enable_async=False,
        )
        assert Jinja2FilterName.TAG not in jinja2_env.filters
        # "format" is a built-in Jinja2 filter, so check it's NOT our async one
        assert jinja2_env.filters.get(Jinja2FilterName.FORMAT) is not async_text_format_filter

    def test_sync_filters_registered_when_async_disabled(self) -> None:
        """Sync filters (escape_script_tag) should be registered regardless of enable_async."""
        jinja2_env = make_jinja2_env_without_loader(
            template_category=TemplateCategory.HTML,
            enable_async=False,
        )
        assert Jinja2FilterName.ESCAPE_SCRIPT_TAG in jinja2_env.filters

    def test_sync_filter_with_images_registered_when_async_disabled(self) -> None:
        """Sync filter (with_images) should be registered even when enable_async is False."""
        jinja2_env = make_jinja2_env_without_loader(
            template_category=TemplateCategory.LLM_PROMPT,
            enable_async=False,
        )
        assert Jinja2FilterName.WITH_IMAGES in jinja2_env.filters

    @pytest.mark.parametrize(
        "template_category",
        [TemplateCategory.EXPRESSION, TemplateCategory.MERMAID],
    )
    def test_categories_without_filters_unaffected(self, template_category: TemplateCategory) -> None:
        """Categories with no custom filters should work in both sync and async modes."""
        for enable_async in (True, False):
            jinja2_env = make_jinja2_env_without_loader(
                template_category=template_category,
                enable_async=enable_async,
            )
            assert Jinja2FilterName.TAG not in jinja2_env.filters
            assert jinja2_env.filters.get(Jinja2FilterName.FORMAT) is not async_text_format_filter
