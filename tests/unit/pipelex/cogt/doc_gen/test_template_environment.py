import pytest
from jinja2.exceptions import SecurityError, TemplateError, UndefinedError
from jinja2.filters import FILTERS as JINJA_FILTERS
from markupsafe import Markup

from pipelex.cogt.doc_gen.exceptions import MarkdownFormattingBudgetError
from pipelex.cogt.doc_gen.formatted_markdown import FormattedMarkdown
from pipelex.cogt.doc_gen.template_environment import make_plain_data_template_environment
from pipelex.tools.jinja2.jinja2_filters import markdown_to_formatted
from pipelex.tools.jinja2.jinja2_render_budget import DEFAULT_RENDER_BUDGET_UNITS, MARKDOWN_UNITS_PER_CHARACTER, RenderBudgetExceededError
from tests.unit.pipelex.tools.markdown.test_data import MarkdownFormattingTestData


def _kinds_of_formatted(value: object) -> object:
    """An engine's finalize: a printed `FormattedMarkdown` as the kinds of its blocks, every other value as it is."""
    if isinstance(value, FormattedMarkdown):
        return "<" + ",".join(block.kind for block in value.blocks) + ">"
    return value


def _marker_for_formatted(value: object) -> object:
    """An engine's finalize printing markup of its own for a `FormattedMarkdown`, every other value as it is."""
    if isinstance(value, FormattedMarkdown):
        return Markup("<?marker?>")
    return value


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

    def test_the_filters_are_jinjas_own_and_markdown(self) -> None:
        # The names with a leading underscore are the render budget's own, which its rewrite of a template calls.
        filters = make_plain_data_template_environment().filters
        named_filters = {name: function for name, function in filters.items() if not name.startswith("_")}
        assert named_filters == {**JINJA_FILTERS, "markdown": markdown_to_formatted}

    def test_markdown_prints_through_the_engine_s_finalize(self) -> None:
        environment = make_plain_data_template_environment(finalize=_kinds_of_formatted)
        rendered = environment.from_string("{{ notes | markdown }}|{{ count }}|{{ title }}").render(
            notes=MarkdownFormattingTestData.NOTES, count=3, title="Invoice"
        )
        assert rendered == "<paragraph,list_item,list_item>|3|Invoice"

    def test_markdown_prints_its_plain_text_without_a_finalize(self) -> None:
        rendered = (
            make_plain_data_template_environment()
            .from_string("{{ invoice.notes | markdown }}")
            .render(invoice={"notes": MarkdownFormattingTestData.NOTES})
        )
        assert rendered == MarkdownFormattingTestData.NOTES_PLAIN_TEXT

    def test_markdown_reads_any_other_value_as_its_text(self) -> None:
        assert make_plain_data_template_environment().from_string("{{ total | markdown }}").render(total=12.5) == "12.5"

    def test_markdown_of_none_prints_nothing(self) -> None:
        environment = make_plain_data_template_environment(finalize=_kinds_of_formatted)
        assert environment.from_string("[{{ notes | markdown }}]").render(notes=None) == "[<>]"
        assert make_plain_data_template_environment().from_string("[{{ notes | markdown }}]").render(notes=None) == "[]"

    @pytest.mark.parametrize(("notes", "expected"), [(None, "no"), ("", "no"), ("   \n\t", "no"), ("Due in *30* days.", "yes")])
    def test_markdown_is_false_when_it_formats_into_nothing(self, notes: str | None, expected: str) -> None:
        template = make_plain_data_template_environment().from_string("{% if notes | markdown %}yes{% else %}no{% endif %}")
        assert template.render(notes=notes) == expected

    def test_markdown_of_a_missing_value_fails_the_render(self) -> None:
        template = make_plain_data_template_environment().from_string("{{ invoice.notes | markdown }}")
        with pytest.raises(UndefinedError):
            template.render(invoice={})

    def test_markdown_under_autoescape_prints_its_plain_text_escaped(self) -> None:
        # docxtpl turns autoescaping on after the environment is built; the engine's markup passes as it is.
        environment = make_plain_data_template_environment(finalize=_marker_for_formatted)
        environment.autoescape = True
        rendered = environment.from_string("{{ notes | markdown }}|{{ raw }}").render(notes="a < b", raw="<?marker?>")
        assert rendered == "<?marker?>|&lt;?marker?&gt;"
        plain_environment = make_plain_data_template_environment()
        plain_environment.autoescape = True
        assert plain_environment.from_string("{{ notes | markdown }}").render(notes="a < **b** & c") == "a &lt; b &amp; c"

    def test_markdown_is_charged_to_the_render_s_budget(self) -> None:
        # Each conversion costs about two fifths of a render's budget: one renders, and a render making three is
        # refused at the third, with the render's own budget error.
        notes = "word " * (DEFAULT_RENDER_BUDGET_UNITS * 2 // 5 // MARKDOWN_UNITS_PER_CHARACTER // 5)
        environment = make_plain_data_template_environment()
        assert environment.from_string("{{ notes | markdown }}").render(notes=notes) == notes.strip()
        template = environment.from_string("{% for i in range(3) %}{{ notes | markdown }}{% endfor %}")
        with pytest.raises(RenderBudgetExceededError, match="formatting Markdown") as caught:
            template.render(notes=notes)
        assert isinstance(caught.value, TemplateError)
        assert not isinstance(caught.value, MarkdownFormattingBudgetError)
