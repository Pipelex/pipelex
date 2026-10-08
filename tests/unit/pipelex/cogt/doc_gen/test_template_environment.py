import pytest
from jinja2.exceptions import SecurityError, UndefinedError
from jinja2.filters import FILTERS as JINJA_FILTERS

from pipelex.cogt.doc_gen.template_environment import make_plain_data_template_environment
from pipelex.tools.jinja2.jinja2_render_budget import DEFAULT_RENDER_BUDGET_UNITS, RenderBudgetExceededError


class TestPlainDataTemplateEnvironment:
    def test_a_template_renders_synchronously(self) -> None:
        environment = make_plain_data_template_environment()
        assert environment.is_async is False
        rendered = environment.from_string("{{ customer.name|upper }} owes {{ '%.2f'|format(total) }}").render(customer={"name": "Ada"}, total=12.5)
        assert rendered == "ADA owes 12.50"

    def test_a_missing_value_fails_the_render(self) -> None:
        template = make_plain_data_template_environment().from_string("Dear {{ customer.name }}")
        with pytest.raises(UndefinedError):
            template.render(customer={})

    @pytest.mark.parametrize(
        ("source", "variables"),
        [
            ("{{ total.__class__ }}", {"total": 3}),
            ("{{ record._secret }}", {"record": {"_secret": "x"}}),
            ("{{ action() }}", {"action": print}),
        ],
    )
    def test_the_sandbox_refuses_what_a_template_may_not_reach(self, source: str, variables: dict[str, object]) -> None:
        template = make_plain_data_template_environment().from_string(source)
        with pytest.raises(SecurityError):
            template.render(**variables)

    def test_a_render_spends_from_a_budget(self) -> None:
        # More iterations than the budget affords at 32 units each, but few enough to end within a second without one.
        template = make_plain_data_template_environment().from_string("{% for i in range(64) %}{% for j in range(inner) %}{% endfor %}{% endfor %}")
        with pytest.raises(RenderBudgetExceededError):
            template.render(inner=DEFAULT_RENDER_BUDGET_UNITS // 64 // 32)

    def test_the_filters_are_jinjas_own(self) -> None:
        # The names with a leading underscore are the render budget's own, which its rewrite of a template calls.
        filters = make_plain_data_template_environment().filters
        named_filters = {name: function for name, function in filters.items() if not name.startswith("_")}
        assert named_filters == JINJA_FILTERS
