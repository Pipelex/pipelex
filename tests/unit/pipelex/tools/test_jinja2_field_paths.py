import pytest

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_field_paths import detect_template_field_paths
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.jinja2_scopes import LIST_ITEM_SEGMENT
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from tests.unit.pipelex.tools.test_jinja2_required_variables import TestData as RequiredVariablesData


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

    @pytest.mark.parametrize(
        ("topic", "template_source"),
        [
            ("set_in_every_branch_rebinds_an_input", "{% if f %}{% set invoice = a %}{% else %}{% set invoice = b %}{% endif %}{{ invoice.nosuch }}"),
            (
                "loop_target_rebound_in_every_branch",
                (
                    "{% for item in invoice.line_items %}{% if f %}{% set item = a %}{% else %}{% set item = b %}{% endif %}"
                    "{{ item.nosuch }}{% endfor %}"
                ),
            ),
            ("set_in_a_call_block_body", "{% call m() %}{% set invoice = a %}{{ invoice.nosuch }}{% endcall %}"),
            ("set_in_a_filter_block_body", "{% filter upper %}{% set invoice = a %}{{ invoice.nosuch }}{% endfilter %}"),
            ("macro_default_reads_an_earlier_argument", "{% macro show(invoice, total=invoice.nosuch) %}{{ total }}{% endmacro %}"),
        ],
    )
    def test_a_name_jinja_binds_gives_no_path(self, topic: str, template_source: str) -> None:
        paths = _paths(template_source)
        assert not any("nosuch" in path for path in paths), f"{topic}: {paths}"

    def test_a_called_global_gives_no_path(self) -> None:
        assert _paths("{% for i in range(3) %}{{ dict(a=i).a }}{% endfor %}") == []

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_path"),
        [
            ("set_in_some_branches", "{% if f %}{% set invoice = other %}{% endif %}{{ invoice.nosuch }}", ("invoice", "nosuch")),
            (
                "loop_target_rebound_in_some_branches",
                "{% for item in invoice.line_items %}{% if f %}{% set item = other %}{% endif %}{{ item.nosuch }}{% endfor %}",
                ("invoice", "line_items", LIST_ITEM_SEGMENT, "nosuch"),
            ),
            ("set_does_not_escape_a_loop", "{% for x in xs %}{% set invoice = x %}{% endfor %}{{ invoice.nosuch }}", ("invoice", "nosuch")),
            (
                "macro_reads_a_name_its_frame_reads_before_setting",
                "{{ invoice }}{% macro m() %}{{ invoice.nosuch }}{% endmacro %}{{ m() }}{% set invoice = other %}",
                ("invoice", "nosuch"),
            ),
            (
                "loop_target_in_a_block",
                "{% for invoice in invoices.all %}{% block b %}{{ invoice.nosuch }}{% endblock %}{% endfor %}",
                ("invoice", "nosuch"),
            ),
            (
                "loop_target_in_a_scoped_block",
                "{% for item in invoice.line_items %}{% block b scoped %}{{ item.nosuch }}{% endblock %}{% endfor %}",
                ("invoice", "line_items", LIST_ITEM_SEGMENT, "nosuch"),
            ),
        ],
    )
    def test_a_name_read_where_jinja_reads_the_input_keeps_its_path(self, topic: str, template_source: str, expected_path: tuple[str, ...]) -> None:
        assert expected_path in _paths(template_source), f"{topic}: {_paths(template_source)}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        RequiredVariablesData.JINJA_SCOPE_RULES,
    )
    def test_roots_match_the_required_variables(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],  # ruff: ignore[unused-method-argument]
    ) -> None:
        """The field paths and the required variables walk the same scopes, so they start from the same inputs."""
        field_path_roots = {
            field_path.root for field_path in detect_template_field_paths(template_source=template_source, template_category=TemplateCategory.HTML)
        }
        required = detect_jinja2_required_variables(template_category=TemplateCategory.HTML, template_source=template_source)
        assert field_path_roots == {get_root_from_dotted_path(path) for path in required}, f"Failed for topic: {topic}"

    def test_a_subscript_is_not_followed(self) -> None:
        assert _paths("{{ invoice['customer'].name }}") == [("invoice",)]

    def test_a_syntax_error_is_reported(self) -> None:
        with pytest.raises(Jinja2DetectVariablesError):
            detect_template_field_paths(template_source="{% for item in %}", template_category=TemplateCategory.HTML)
