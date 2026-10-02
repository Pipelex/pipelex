import pytest

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_field_paths import LIST_ITEM_SEGMENT, detect_template_field_paths
from pipelex.tools.jinja2.template_category import TemplateCategory


def _paths(template_source: str) -> list[tuple[str, ...]]:
    found = detect_template_field_paths(template_source=template_source, template_category=TemplateCategory.HTML)
    return [(field_path.root, *field_path.segments) for field_path in found]


class TestDetectTemplateFieldPaths:
    def test_an_attribute_chain_reads_its_path(self) -> None:
        assert _paths("{{ invoice.customer.name }}") == [("invoice", "customer", "name")]

    def test_a_loop_variable_reads_an_item_of_the_iterated_list(self) -> None:
        paths = _paths("{% for item in invoice.line_items %}{{ item.amount }}{% endfor %}")
        assert paths == [("invoice", "line_items"), ("invoice", "line_items", LIST_ITEM_SEGMENT, "amount")]

    def test_nested_loops_follow_each_level(self) -> None:
        paths = _paths("{% for section in report.sections %}{% for row in section.rows %}{{ row.label }}{% endfor %}{% endfor %}")
        assert ("report", "sections", LIST_ITEM_SEGMENT, "rows", LIST_ITEM_SEGMENT, "label") in paths

    def test_the_written_chain_is_kept_for_messages(self) -> None:
        found = detect_template_field_paths(
            template_source="{% for item in invoice.line_items %}{{ item.amount }}{% endfor %}", template_category=TemplateCategory.HTML
        )
        assert found[-1].written == "item.amount"

    @pytest.mark.parametrize(
        ("topic", "template_source"),
        [
            ("set_alias", "{% set customer = invoice.customer %}{{ customer.nosuch }}"),
            ("with_alias", "{% with customer = invoice.customer %}{{ customer.nosuch }}{% endwith %}"),
            ("macro_argument", "{% macro show(customer) %}{{ customer.nosuch }}{% endmacro %}"),
            ("tuple_loop_target", "{% for key, value in invoice.pairs %}{{ value.nosuch }}{% endfor %}"),
            ("loop_helper", "{% for item in invoice.line_items %}{{ loop.index }}{% endfor %}"),
        ],
    )
    def test_what_cannot_be_followed_gives_no_path_through_it(self, topic: str, template_source: str) -> None:
        paths = _paths(template_source)
        assert not any("nosuch" in path or "index" in path for path in paths), f"{topic}: {paths}"

    def test_a_subscript_is_not_followed(self) -> None:
        assert _paths("{{ invoice['customer'].name }}") == [("invoice",)]

    def test_a_syntax_error_is_reported(self) -> None:
        with pytest.raises(Jinja2DetectVariablesError):
            detect_template_field_paths(template_source="{% for item in %}", template_category=TemplateCategory.HTML)
