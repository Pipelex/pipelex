import tracemalloc

import pytest
from jinja2.exceptions import TemplateError
from pydantic import BaseModel

from pipelex.cogt.doc_gen import formatted_markdown
from pipelex.cogt.doc_gen.exceptions import MarkdownFormattingBudgetError
from pipelex.cogt.doc_gen.formatted_markdown import FormattedHeading, FormattedParagraph, TextSpan, format_markdown
from pipelex.tools.jinja2.jinja2_render_budget import (
    DEFAULT_RENDER_BUDGET_UNITS,
    MARKDOWN_UNITS_PER_CHARACTER,
    RenderBudget,
    RenderBudgetExceededError,
    active_render_budget,
    spending_from,
)
from pipelex.tools.markdown import markdown_formatting, markdown_rules
from pipelex.tools.markdown.markdown_parser import table_cells_bound
from tests.unit.pipelex.tools.markdown.test_data import MarkdownFormattingTestData

# What a conversion refused for its tables may hold before the refusal: its source and the scan of its lines, never the
# tokens of its cells, which take tens of megabytes here.
_REFUSED_BEFORE_PARSING_PEAK_BYTES = 4 * 1024 * 1024


class TestFormattedMarkdown:
    def test_the_contract_names_the_structure_it_formats_into(self) -> None:
        """An engine imports the structure from the contract, which names the very classes the conversion builds, all of them."""
        models = [value for value in vars(markdown_formatting).values() if isinstance(value, type) and issubclass(value, BaseModel)]
        public_models = {
            model.__name__ for model in models if model.__module__ == markdown_formatting.__name__ and not model.__name__.startswith("_")
        }
        assert public_models
        assert public_models <= set(formatted_markdown.__all__)
        for name in formatted_markdown.__all__:
            if name == "format_markdown":
                continue
            source = markdown_formatting if hasattr(markdown_formatting, name) else markdown_rules
            assert getattr(formatted_markdown, name) is getattr(source, name), name
        assert isinstance(format_markdown(markdown="Hello"), markdown_formatting.FormattedMarkdown)

    def test_it_formats_by_the_shared_rules(self) -> None:
        assert format_markdown(markdown="# Report\n\nSee [the site](https://pipelex.com).").blocks == [
            FormattedHeading(level=1, spans=[TextSpan(text="Report")]),
            FormattedParagraph(spans=[TextSpan(text="See "), TextSpan(text="the site", link="https://pipelex.com"), TextSpan(text=".")]),
        ]

    def test_outside_a_render_its_own_budget_refuses_a_padded_table_before_parsing_it(self) -> None:
        tracemalloc.start()
        try:
            with pytest.raises(MarkdownFormattingBudgetError, match="outside a template render"):
                format_markdown(markdown=MarkdownFormattingTestData.PADDED_TABLE)
            _, peak_bytes = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        assert peak_bytes < _REFUSED_BEFORE_PARSING_PEAK_BYTES
        assert active_render_budget() is None

    def test_a_reference_used_thousands_of_times_is_refused_before_it_is_built(self) -> None:
        with pytest.raises(MarkdownFormattingBudgetError):
            format_markdown(markdown=MarkdownFormattingTestData.REUSED_REFERENCE)

    def test_outside_a_render_an_ordinary_long_text_formats(self) -> None:
        formatted = format_markdown(markdown=MarkdownFormattingTestData.LONG_REPORT)
        assert sum(isinstance(block, FormattedHeading) for block in formatted.blocks) == 300

    def test_the_budget_error_is_the_caller_s(self) -> None:
        with pytest.raises(MarkdownFormattingBudgetError) as caught:
            format_markdown(markdown=MarkdownFormattingTestData.PADDED_TABLE)
        report = caught.value.to_error_report()
        assert report.error_domain == "input"
        assert report.caller_facing_message
        assert f"{DEFAULT_RENDER_BUDGET_UNITS:,} work units" in caught.value.message

    def test_inside_a_render_the_render_s_budget_is_charged_for_the_source_the_tables_and_the_result(self) -> None:
        """A table of padded cells costs more to parse than its result takes: dropping either charge spends less."""
        markdown = MarkdownFormattingTestData.WIDE_SHORT_TABLE
        source_and_tables = MARKDOWN_UNITS_PER_CHARACTER * (len(markdown) + table_cells_bound(markdown_text=markdown))
        budget = RenderBudget(total=DEFAULT_RENDER_BUDGET_UNITS)
        with spending_from(budget=budget):
            format_markdown(markdown=markdown)
        spent = DEFAULT_RENDER_BUDGET_UNITS - budget.remaining
        assert spent > source_and_tables

    def test_inside_a_render_an_overdraft_is_the_render_s_own_template_error(self) -> None:
        # A budget that affords the text alone, not the conversion: the refusal is the render's, which a template fill
        # catches with every other template error.
        budget = RenderBudget(total=len(MarkdownFormattingTestData.NOTES) * 4)
        with spending_from(budget=budget), pytest.raises(RenderBudgetExceededError, match="formatting Markdown") as caught:
            format_markdown(markdown=MarkdownFormattingTestData.NOTES)
        assert isinstance(caught.value, TemplateError)
        assert not isinstance(caught.value, MarkdownFormattingBudgetError)
