import pytest

from pipelex.cogt.templating.template_rendering import render_template
from pipelex.tools.jinja2.exceptions import Jinja2TemplateRenderError
from pipelex.tools.jinja2.template_category import TemplateCategory


@pytest.mark.asyncio
class TestStrictUndefined:
    async def test_a_missing_field_fails_the_render(self) -> None:
        with pytest.raises(Jinja2TemplateRenderError):
            await render_template(
                "{{ invoice.nosuch }}", category=TemplateCategory.BASIC, context={"invoice": {"number": "INV-1"}}, is_undefined_strict=True
            )

    async def test_the_default_undefined_still_prints_nothing(self) -> None:
        rendered = await render_template("[{{ invoice.nosuch }}]", category=TemplateCategory.BASIC, context={"invoice": {"number": "INV-1"}})
        assert rendered == "[]"

    @pytest.mark.parametrize(
        "template",
        [
            "{% if notes %}{{ notes }}{% else %}none{% endif %}",
            "{% if notes is defined %}{{ notes }}{% else %}none{% endif %}",
            "{{ notes | default('none') }}",
        ],
    )
    async def test_an_absent_optional_input_can_be_tested(self, template: str) -> None:
        rendered = await render_template(template, category=TemplateCategory.BASIC, context={}, is_undefined_strict=True)
        assert rendered == "none"
