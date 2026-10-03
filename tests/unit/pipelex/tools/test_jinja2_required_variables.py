from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
from jinja2 import Environment, UndefinedError
from typing_extensions import override

from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import (
    detect_jinja2_required_variables,
    detect_jinja2_variable_references,
)
from pipelex.tools.jinja2.jinja2_undefined import PresenceProbingStrictUndefined
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class _PermissiveValue:
    """A context value any template shape can read: every attribute and call gives itself back."""

    def __init__(self, *, is_truthy: bool) -> None:
        self.is_truthy = is_truthy

    def __getattr__(self, name: str) -> "_PermissiveValue":
        if name.startswith("__"):
            raise AttributeError(name)
        return self

    def __call__(self, *_args: Any, **_kwargs: Any) -> "_PermissiveValue":
        return self

    def __iter__(self) -> Iterator["_PermissiveValue"]:
        return iter([self] if self.is_truthy else [])

    def __bool__(self) -> bool:
        return self.is_truthy

    @override
    def __str__(self) -> str:
        return "value"


class TestData:
    """Test data for detect_jinja2_required_variables tests.

    Note: The function returns ONLY the leaf (full) paths, not intermediate paths.
    For example, `{{ foo.bar.baz }}` returns `{"foo.bar.baz"}`, NOT `{"foo", "foo.bar", "foo.bar.baz"}`.
    """

    # (topic, template_source, expected_variables)
    SIMPLE_VARIABLES: ClassVar[list[tuple[str, str, set[str]]]] = [
        ("single_variable", "Hello {{ name }}", {"name"}),
        ("two_variables", "{{ first }} and {{ second }}", {"first", "second"}),
        ("variable_in_sentence", "The value is {{ value }} today", {"value"}),
        ("variable_with_spaces", "{{   spaced   }}", {"spaced"}),
        ("empty_template", "No variables here", set()),
        ("just_text", "Plain text without any jinja", set()),
    ]

    MULTIPLE_VARIABLES: ClassVar[list[tuple[str, str, set[str]]]] = [
        (
            "three_variables",
            "Name: {{ name }}, Age: {{ age }}, City: {{ city }}",
            {"name", "age", "city"},
        ),
        (
            "five_variables_multiline",
            """
            Name: {{ name }}
            Age: {{ age }}
            Email: {{ email }}
            Phone: {{ phone }}
            Address: {{ address }}
            """,
            {"name", "age", "email", "phone", "address"},
        ),
        (
            "repeated_variable",
            "{{ var }} is the same as {{ var }}",
            {"var"},  # Should detect only once
        ),
    ]

    NESTED_VARIABLES: ClassVar[list[tuple[str, str, set[str]]]] = [
        # Full paths are returned
        ("simple_dot_notation", "{{ user.name }}", {"user.name"}),
        ("deep_nesting", "{{ user.profile.bio.short }}", {"user.profile.bio.short"}),
        (
            "multiple_nested",
            "{{ user.name }} and {{ config.setting }}",
            {"user.name", "config.setting"},
        ),
        (
            "mix_nested_and_simple",
            "Hello {{ name }}, your email is {{ user.email }}",
            {"name", "user.email"},
        ),
    ]

    VARIABLES_WITH_FILTERS: ClassVar[list[tuple[str, str, set[str]]]] = [
        ("single_filter", '{{ name|tag("name") }}', {"name"}),
        ("format_filter", "{{ amount|format() }}", {"amount"}),
        ("chained_filters", "{{ value|lower|upper }}", {"value"}),
        (
            "filter_with_argument",
            "{{ text|truncate(50) }}",
            {"text"},
        ),
        (
            "multiple_vars_with_filters",
            '{{ first|tag("first") }} and {{ second|format() }}',
            {"first", "second"},
        ),
        (
            "nested_with_filter",
            '{{ user.name|tag("user.name") }}',
            {"user.name"},
        ),
    ]

    CONTROL_STRUCTURES: ClassVar[list[tuple[str, str, set[str]]]] = [
        (
            "if_statement",
            "{% if show_name %}{{ name }}{% endif %}",
            {"show_name", "name"},
        ),
        (
            "if_else_statement",
            "{% if condition %}{{ yes_value }}{% else %}{{ no_value }}{% endif %}",
            {"condition", "yes_value", "no_value"},
        ),
        (
            "for_loop",
            "{% for item in items %}{{ item }}{% endfor %}",
            {"items"},  # 'item' is defined within the loop
        ),
        (
            "for_loop_with_extra_var",
            "{% for item in items %}{{ item }} ({{ prefix }}){% endfor %}",
            {"items", "prefix"},  # 'item' is loop var, items and prefix are external
        ),
        (
            "nested_for_loops",
            "{% for row in rows %}{% for cell in row.cells %}{{ cell }}{% endfor %}{% endfor %}",
            {"rows"},
        ),
        (
            "for_loop_with_nested_external",
            "{% for item in items %}{{ item.name }} ({{ prefix.value }}){% endfor %}",
            {"items", "prefix.value"},
        ),
    ]

    COMPLEX_REAL_WORLD: ClassVar[list[tuple[str, str, set[str]]]] = [
        (
            "gantt_chart_analysis",
            """I am sharing an image of a Gantt chart: {{ gantt_chart_image|format() }}.
Please analyse the image and for a given task name (and only this task), extract the information of the task, if relevant.

Be careful, the time unit is this:
{{ gantt_timescale|tag("gantt_timescale") }}

If the task is a milestone, then only output the start_date.

Here is the name of the task you have to extract the dates for:
{{ gantt_task_name|tag("gantt_task_name") }}""",
            {"gantt_chart_image", "gantt_timescale", "gantt_task_name"},
        ),
        (
            "invoice_extraction",
            """Extract employee information from this invoice text: {{ invoice_text|tag("invoice_text") }}.

The company details are:
{{ company_info|format() }}

Please extract the following fields:
- Employee name
- Employee ID
- Department""",
            {"invoice_text", "company_info"},
        ),
        (
            "email_template",
            """Dear {{ recipient.name }},

{% if greeting %}{{ greeting }}{% else %}Hello{% endif %}

We are writing to inform you about {{ topic }}.

{% for item in action_items %}
- {{ item }}
{% endfor %}

Best regards,
{{ sender.name }}
{{ sender.title }}""",
            {"recipient.name", "greeting", "topic", "action_items", "sender.name", "sender.title"},
        ),
    ]

    OPTIONAL_VARIABLES: ClassVar[list[tuple[str, str, set[str]]]] = [
        (
            "optional_with_if",
            '{% if optional_field %}{{ optional_field|tag("optional_field") }}{% endif %}',
            {"optional_field"},
        ),
        (
            "optional_nested",
            '{% if user.bio %}{{ user.bio|tag("user.bio") }}{% endif %}',
            {"user.bio"},
        ),
    ]

    MTHDS_STYLE_TEMPLATES: ClassVar[list[tuple[str, str, set[str]]]] = [
        (
            "mthds_at_variable_preprocessed",
            '{{ page.page_view|tag("page.page_view") }}',
            {"page.page_view"},
        ),
        (
            "mthds_dollar_variable_preprocessed",
            "{{ page.text_and_images.text.text|format() }}",
            {"page.text_and_images.text.text"},
        ),
        (
            "mthds_mixed_preprocessed",
            '{{ page.page_view|tag("page.page_view") }}\n{{ page.text_and_images.text.text|format() }}',
            {"page.page_view", "page.text_and_images.text.text"},
        ),
    ]

    # A path stops at a subscript, a call or a filter, and the read before it still counts
    CHAINED_ACCESS: ClassVar[list[tuple[str, str, set[str]]]] = [
        ("attribute_after_subscript", "{{ items[0].text }}", {"items"}),
        ("attribute_after_subscript_on_a_path", "{{ a.items[0].name }}", {"a.items"}),
        ("attribute_after_key", "{{ record['meta'].title }}", {"record"}),
        ("attribute_after_call", "{{ a.get('k').x }}", {"a.get"}),
        ("attribute_after_filter", "{{ (items|first).text }}", {"items"}),
        ("attribute_after_subscript_on_a_loop_variable", "{% for row in rows %}{{ row[0].text }}{% endfor %}", {"rows"}),
    ]

    # A `set` declares its name from that statement on, so what it reads, and a read before it, are required
    ASSIGNMENT_ORDER: ClassVar[list[tuple[str, str, set[str]]]] = [
        ("self_referential_set", "{% set topic = topic|trim %}{{ topic }}", {"topic"}),
        ("read_before_set", "{{ note }}{% set note = 'x' %}{{ note }}", {"note"}),
        ("read_after_set", "{% set note = 'x' %}{{ note }}", set()),
        ("read_after_block_set", "{% set note %}{{ body }}{% endset %}{{ note }}", {"body"}),
        ("macro_reads_a_later_set", "{{ x }}{% macro m() %}[{{ g }}]{% endmacro %}{% set g = 'y' %}{{ m() }}", {"x"}),
    ]

    # Where Jinja binds a name a template sets. An `if` opens no frame, and after it a name every branch sets, the
    # `else` included, is bound, while a name only some branches set is the input of that name on the paths where
    # none ran. A loop body, a loop's `else`, a macro, a call, filter or set block, a `with` and `autoescape` each
    # open a frame, so a set inside one stays inside it
    JINJA_SCOPE_RULES: ClassVar[list[tuple[str, str, set[str]]]] = [
        ("set_read_later_in_its_if_branch", "{% if x %}{% set y = 1 %}{{ y }}{% endif %}", {"x"}),
        ("set_in_both_branches", "{% if x %}{% set y = 1 %}{% else %}{% set y = 2 %}{% endif %}{{ y }}", {"x"}),
        (
            "set_in_every_branch_with_elifs",
            "{% if a %}{% set y = 1 %}{% elif b %}{% set y = 2 %}{% else %}{% set y = 3 %}{% endif %}{{ y }}",
            {"a", "b"},
        ),
        ("set_in_some_branches", "{% if x %}{% set y = 1 %}{% endif %}{{ y }}", {"x", "y"}),
        ("set_in_every_branch_but_no_else", "{% if a %}{% set y = 1 %}{% elif b %}{% set y = 2 %}{% endif %}{{ y }}", {"a", "b", "y"}),
        ("set_missing_from_an_elif", "{% if a %}{% set y = 1 %}{% elif b %}-{% else %}{% set y = 3 %}{% endif %}{{ y }}", {"a", "b", "y"}),
        ("else_does_not_see_the_body_set", "{% if x %}{% set y = 1 %}{% else %}{{ y }}{% endif %}", {"x", "y"}),
        ("elif_test_does_not_see_the_body_set", "{% if x %}{% set y = 1 %}{% elif y %}-{% endif %}", {"x", "y"}),
        (
            "nested_ifs_set_in_every_branch",
            "{% if a %}{% if b %}{% set y = 1 %}{% else %}{% set y = 2 %}{% endif %}{% else %}{% set y = 3 %}{% endif %}{{ y }}",
            {"a", "b"},
        ),
        ("nested_if_without_else", "{% if a %}{% if b %}{% set y = 1 %}{% endif %}{% else %}{% set y = 3 %}{% endif %}{{ y }}", {"a", "b", "y"}),
        ("set_before_the_if_and_in_a_branch", "{% set y = 1 %}{% if x %}{% set y = 2 %}{% endif %}{{ y }}", {"x"}),
        ("read_before_set_in_a_branch", "{% if x %}{{ y }}{% set y = 1 %}{% endif %}", {"x", "y"}),
        ("set_read_later_in_a_loop_body", "{% for i in items %}{% set day = i.d %}{{ day }}{% endfor %}", {"items"}),
        ("read_before_set_in_a_loop_body", "{% for i in items %}[{{ y }}]{% set y = i %}{% endfor %}", {"items", "y"}),
        ("set_in_some_branches_inside_a_loop", "{% for i in items %}{% if i %}{% set y = i %}{% endif %}{{ y }}{% endfor %}", {"items", "y"}),
        ("set_in_a_loop_else", "{% for i in items %}-{% else %}{% set y = 1 %}{{ y }}{% endfor %}", {"items"}),
        ("set_in_a_with_body", "{% with %}{% set y = 1 %}{{ y }}{% endwith %}", set()),
        ("set_in_a_macro_body", "{% macro m() %}{% set y = 1 %}{{ y }}{% endmacro %}{{ m() }}", set()),
        ("set_in_a_call_block_body", "{% macro m() %}{{ caller() }}{% endmacro %}{% call m() %}{% set y = 1 %}{{ y }}{% endcall %}", set()),
        ("set_in_a_filter_block_body", "{% filter upper %}{% set y = 'a' %}{{ y }}{% endfilter %}", set()),
        ("set_in_a_set_block_body", "{% set z %}{% set y = 'a' %}{{ y }}{% endset %}{{ z }}", set()),
        ("set_in_an_autoescape_block", "{% autoescape true %}{% set y = 1 %}{{ y }}{% endautoescape %}", set()),
        ("set_does_not_escape_a_loop", "{% for i in items %}{% set y = i %}{% endfor %}{{ y }}", {"items", "y"}),
        ("set_does_not_escape_a_loop_else", "{% for i in items %}-{% else %}{% set y = 1 %}{% endfor %}{{ y }}", {"items", "y"}),
        ("set_does_not_escape_a_with", "{% with %}{% set y = 1 %}{% endwith %}{{ y }}", {"y"}),
        ("set_does_not_escape_a_macro", "{% macro m() %}{% set y = 1 %}{% endmacro %}{{ m() }}{{ y }}", {"y"}),
        ("set_does_not_escape_a_call_block", "{% macro m() %}{{ caller() }}{% endmacro %}{% call m() %}{% set y = 1 %}{% endcall %}{{ y }}", {"y"}),
        ("set_does_not_escape_a_filter_block", "{% filter upper %}{% set y = 'a' %}{% endfilter %}{{ y }}", {"y"}),
        ("set_does_not_escape_a_set_block", "{% set z %}{% set y = 'a' %}{% endset %}{{ z }}{{ y }}", {"y"}),
        ("set_does_not_escape_an_autoescape_block", "{% autoescape true %}{% set y = 1 %}{% endautoescape %}{{ y }}", {"y"}),
        ("with_target", "{% with y = 1 %}{{ y }}{% endwith %}", set()),
        ("with_value_reads_outside_the_with", "{% with a = 1, b = a %}{{ b }}{% endwith %}", {"a"}),
        ("tuple_target", "{% set a, b = 1, 2 %}{{ a }}{{ b }}", set()),
        ("nested_tuple_target", "{% set a, (b, c) = 1, (2, 3) %}{{ a }}{{ c }}", set()),
        ("nested_tuple_loop_target", "{% for k, (a, b) in [(1, (2, 3))] %}{{ k }}{{ b }}{% endfor %}", set()),
        (
            "namespace_attribute_set_in_an_if",
            "{% set ns = namespace(found=false) %}{% for i in items %}{% if i %}{% set ns.found = true %}{% endif %}{% endfor %}{{ ns.found }}",
            {"items"},
        ),
        (
            "macro_reads_a_name_every_branch_sets",
            "{% if a %}{% set g = 1 %}{% else %}{% set g = 2 %}{% endif %}{% macro m() %}{{ g }}{% endmacro %}{{ m() }}",
            {"a"},
        ),
        ("macro_reads_a_name_some_branches_set", "{% if a %}{% set g = 1 %}{% endif %}{% macro m() %}{{ g }}{% endmacro %}{{ m() }}", {"a", "g"}),
        (
            "macro_in_a_loop_reads_a_later_set",
            "{% for i in items %}{% macro m() %}{{ y }}{% endmacro %}{% set y = i %}{{ m() }}{% endfor %}",
            {"items"},
        ),
        ("macro_called_before_its_definition", "{{ m() }}{% macro m() %}-{% endmacro %}", {"m"}),
        # A frame that reads a name before setting it starts its own copy from the input, which a macro called before
        # the set then reads
        ("macro_reads_a_name_its_frame_reads_before_setting", "{{ a }}{% macro m() %}{{ a.x }}{% endmacro %}{{ m() }}{% set a = 1 %}", {"a", "a.x"}),
        (
            "macro_in_a_loop_reads_a_name_the_loop_reads_before_setting",
            "{% for i in items %}{% if a is defined %}-{% endif %}{% macro m() %}{{ a.x }}{% endmacro %}{{ m() }}{% set a = i %}{% endfor %}",
            {"items", "a", "a.x"},
        ),
        # An `if` opens no frame, so a macro defined in one of its branches sees what its frame sets
        (
            "macro_in_an_if_branch_reads_a_later_set",
            "{% if c %}{% macro m() %}{{ a }}{% endmacro %}{% else %}{% macro m() %}x{% endmacro %}{% endif %}{% set a = 1 %}{{ m() }}",
            {"c"},
        ),
        (
            "macro_in_an_if_branch_in_a_loop_reads_a_later_set",
            (
                "{% for i in items %}{% if c %}{% macro m() %}{{ a }}{% endmacro %}{% else %}{% macro m() %}x{% endmacro %}{% endif %}"
                "{% set a = i %}{{ m() }}{% endfor %}"
            ),
            {"items", "c"},
        ),
        ("macro_default_reads_an_earlier_argument", "{% macro m(a, b=a) %}{{ b }}{% endmacro %}{{ m(1) }}", set()),
        ("call_block_arguments", "{% macro m() %}{{ caller(1) }}{% endmacro %}{% call(a) m() %}{{ a }}{% endcall %}", set()),
        ("filter_block_filter_reads_its_body_set", "{% filter replace('a', y) %}{% set y = 'b' %}a{% endfilter %}", set()),
        # A block runs as a function of its own. Without `scoped` it reads the template context, which holds what the top
        # level has set for certain before it and nothing of a loop, a macro or any other frame around it; a scoped
        # block reads the names bound where it stands, and so do the blocks nested in it
        ("set_in_a_block_body", "{% block b %}{% set y = 1 %}{{ y }}{% endblock %}", set()),
        ("set_does_not_escape_a_block", "{% block b %}{% set y = 1 %}{% endblock %}{{ y }}", {"y"}),
        ("top_level_set_reaches_a_block", "{% set y = 1 %}{% block b %}{{ y }}{% endblock %}", set()),
        ("top_level_set_after_a_block", "{% block b %}{{ y }}{% endblock %}{% set y = 1 %}", {"y"}),
        (
            "set_in_every_top_level_branch_reaches_a_block",
            "{% if x %}{% set y = 1 %}{% else %}{% set y = 2 %}{% endif %}{% block b %}{{ y }}{% endblock %}",
            {"x"},
        ),
        ("set_in_some_top_level_branches_before_a_block", "{% if x %}{% set y = 1 %}{% endif %}{% block b %}{{ y }}{% endblock %}", {"x", "y"}),
        ("set_earlier_in_a_top_level_branch_reaches_a_block", "{% if x %}{% set y = 1 %}{% block b %}{{ y }}{% endblock %}{% endif %}", {"x"}),
        ("top_level_macro_reaches_a_block", "{% macro m() %}-{% endmacro %}{% block b %}{{ m() }}{% endblock %}", set()),
        (
            "loop_target_does_not_reach_a_block",
            "{% for item in items %}{% block b %}{{ item.name }}{% endblock %}{% endfor %}",
            {"items", "item.name"},
        ),
        ("loop_set_does_not_reach_a_block", "{% for i in items %}{% set y = i %}{% block b %}{{ y }}{% endblock %}{% endfor %}", {"items", "y"}),
        (
            "top_level_set_reaches_a_block_in_a_loop",
            "{% set y = 1 %}{% for i in items %}{% set y = i %}{% block b %}{{ y }}{% endblock %}{% endfor %}",
            {"items"},
        ),
        ("with_target_does_not_reach_a_block", "{% with y = 1 %}{% block b %}{{ y }}{% endblock %}{% endwith %}", {"y"}),
        ("macro_argument_does_not_reach_a_block", "{% macro m(a) %}{% block b %}{{ a }}{% endblock %}{% endmacro %}{{ m(1) }}", {"a"}),
        (
            "call_block_argument_does_not_reach_a_block",
            "{% macro m() %}{{ caller(1) }}{% endmacro %}{% call(y) m() %}{% block b %}{{ y }}{% endblock %}{% endcall %}",
            {"y"},
        ),
        ("autoescape_set_does_not_reach_a_block", "{% autoescape true %}{% set y = 1 %}{% block b %}{{ y }}{% endblock %}{% endautoescape %}", {"y"}),
        ("block_set_does_not_reach_a_nested_block", "{% block outer %}{% set z = 1 %}{% block inner %}{{ z }}{% endblock %}{% endblock %}", {"z"}),
        ("scoped_block_sees_the_loop", "{% for item in items %}{% block b scoped %}{{ item.name }}{% endblock %}{% endfor %}", {"items"}),
        (
            "block_nested_in_a_scoped_block_sees_its_call_site",
            "{% for item in items %}{% block outer scoped %}{% block inner %}{{ item.name }}{% endblock %}{% endblock %}{% endfor %}",
            {"items"},
        ),
        (
            "scoped_block_set_does_not_reach_a_nested_block",
            "{% for i in items %}{% block outer scoped %}{% set z = i %}{% block inner %}{{ z }}{% endblock %}{% endblock %}{% endfor %}",
            {"items", "z"},
        ),
    ]

    # Names Jinja provides, and the scope a loop opens, are never inputs
    SCOPES: ClassVar[list[tuple[str, str, set[str]]]] = [
        ("namespace_idiom", "{% set ns = namespace(found=false) %}{{ ns.found }}", set()),
        ("global_followed_by_attribute", "{{ dict(a=1).a }}", set()),
        ("global_called_on_an_input", "{{ range(count) }}", {"count"}),
        ("macro_internal_names", "{% macro m() %}{{ caller().strip() }}{{ varargs }}{{ kwargs }}{% endmacro %}", set()),
        ("loop_target_shadows_its_iterable", "{% for item in item %}{{ item }}{% endfor %}", {"item"}),
        ("else_branch_reads_outside_the_loop", "{% for x in xs %}{{ x }}{% else %}{{ x }}{% endfor %}", {"xs", "x"}),
        ("loop_filter_reads_inside_the_loop", "{% for x in xs if x.ok %}{{ x }}{% endfor %}", {"xs"}),
    ]

    # A Jinja global is Jinja's only where it is called; any other read of its name reads the input that shadows it
    GLOBAL_NAMES_AS_INPUTS: ClassVar[list[tuple[str, str, set[str]]]] = [
        ("bare_global_name", "Summarize the price {{ range }}", {"range"}),
        ("attribute_on_a_global_name", "{{ namespace.name }}", {"namespace.name"}),
        ("filtered_global_name", "{{ dict|upper }}", {"dict"}),
        ("global_name_read_and_called", "{{ range }}{% for i in range(3) %}{{ i }}{% endfor %}", {"range"}),
    ]

    # The reference walk shares the required-variables walk's scopes, so both see the same names read
    REFERENCE_SCOPES: ClassVar[list[tuple[str, str, set[str]]]] = [
        ("self_referential_set", "{% set image = image %}{{ image }}", {"image"}),
        ("read_before_set", "{{ image }}{% set image = 'x' %}{{ image }}", {"image"}),
        ("loop_target_shadows_its_iterable", "{% for images in images %}{{ images }}{% endfor %}", {"images"}),
        ("else_branch_reads_outside_the_loop", "{% for x in xs %}{{ x }}{% else %}{{ x|upper }}{% endfor %}", {"xs", "x"}),
        ("macro_internal_names", "{% macro m() %}{{ caller() }}{{ varargs }}{% endmacro %}", set()),
        ("global_called_on_an_input", "{{ range(count) }}", {"count"}),
        ("bare_global_name", "{{ range }}", {"range"}),
    ]

    TEMPLATE_CATEGORIES: ClassVar[list[TemplateCategory]] = [
        TemplateCategory.BASIC,
        TemplateCategory.LLM_PROMPT,
        TemplateCategory.HTML,
        TemplateCategory.MARKDOWN,
        TemplateCategory.EXPRESSION,
        TemplateCategory.IMG_GEN_PROMPT,
        TemplateCategory.MERMAID,
    ]

    # Error test cases
    SYNTAX_ERRORS: ClassVar[list[tuple[str, str]]] = [
        ("unclosed_brace", "{{ unclosed"),
        ("unclosed_block", "{% if condition %}missing endif"),
        ("invalid_filter_syntax", "{{ value|filter( }}"),
        ("unmatched_endif", "{% endif %}"),
        ("broken_for_loop", "{% for item in %}{{ item }}{% endfor %}"),
    ]


class TestDetectJinja2Variables:
    """Tests for detect_jinja2_required_variables function."""

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.SIMPLE_VARIABLES,
    )
    def test_simple_variables(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """Test detection of simple single and double variable templates."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.MULTIPLE_VARIABLES,
    )
    def test_multiple_variables(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """Test detection of multiple variables in templates."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.NESTED_VARIABLES,
    )
    def test_nested_variables(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """Test detection of nested/dotted variables returns full paths."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.VARIABLES_WITH_FILTERS,
    )
    def test_variables_with_filters(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """Test detection of variables used with Jinja2 filters."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.CONTROL_STRUCTURES,
    )
    def test_control_structures(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """Test detection of variables in control structures (if, for, etc.)."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.COMPLEX_REAL_WORLD,
    )
    def test_complex_real_world_templates(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """Test detection in complex real-world template scenarios."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.OPTIONAL_VARIABLES,
    )
    def test_optional_variables(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """Test detection of optional variables wrapped in if statements."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_paths"),
        TestData.MTHDS_STYLE_TEMPLATES,
    )
    def test_mthds_style_templates(
        self,
        topic: str,
        template_source: str,
        expected_paths: set[str],
    ):
        """Test detection in MTHDS-style preprocessed templates with tag/format filters."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_paths, f"Failed for topic: {topic}"

    @pytest.mark.parametrize("template_category", TestData.TEMPLATE_CATEGORIES)
    def test_different_template_categories(
        self,
        template_category: TemplateCategory,
    ):
        """Test that variable detection works across all template categories."""
        template_source = "Hello {{ name }}, welcome to {{ place }}"
        expected = {"name", "place"}

        result = detect_jinja2_required_variables(
            template_category=template_category,
            template_source=template_source,
        )
        assert result == expected, f"Failed for category: {template_category}"

    def test_empty_template(self):
        """Test that empty template returns empty set."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="",
        )
        assert result == set()

    def test_whitespace_only_template(self):
        """Test that whitespace-only template returns empty set."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="   \n\t\n   ",
        )
        assert result == set()

    @pytest.mark.parametrize(
        ("topic", "template_source"),
        TestData.SYNTAX_ERRORS,
    )
    def test_syntax_errors_raise_exception(
        self,
        topic: str,  # ruff: ignore[unused-method-argument]
        template_source: str,
    ):
        """Test that invalid templates raise Jinja2DetectVariablesError."""
        with pytest.raises(Jinja2DetectVariablesError):
            detect_jinja2_required_variables(
                template_category=TemplateCategory.LLM_PROMPT,
                template_source=template_source,
            )

    def test_set_with_variable(self):
        """Test that set statements don't add their target to required variables."""
        template_source = """
        {% set computed = base_value * 2 %}
        Result: {{ computed }} from {{ base_value }}
        """
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        # 'computed' is defined in the template, only base_value is required
        assert result == {"base_value"}

    def test_macro_variables(self):
        """Test variables inside macro definitions."""
        template_source = """
        {% macro render_item(item) %}
            <div>{{ item.name }}</div>
        {% endmacro %}
        {{ render_item(my_item) }}
        {{ external_var }}
        """
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        # my_item and external_var are required; item is macro parameter
        assert result == {"my_item", "external_var"}

    def test_variables_with_default_filter(self):
        """Test variables with default filter."""
        template_source = '{{ name|default("Anonymous") }} - {{ age|default(0) }}'
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"name", "age"}

    def test_complex_expressions(self):
        """Test variables in complex expressions."""
        template_source = """
        {% if items|length > 0 and show_items %}
            {% for item in items %}
                {{ item.name }}: {{ item.price * quantity }}
            {% endfor %}
        {% endif %}
        """
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"items", "show_items", "quantity"}

    def test_arithmetic_operations(self):
        """Test variables in arithmetic operations."""
        template_source = "Total: {{ price * quantity + tax - discount }}"
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"price", "quantity", "tax", "discount"}

    def test_comparison_operations(self):
        """Test variables in comparison operations."""
        template_source = "{% if age >= min_age and age <= max_age %}Valid{% endif %}"
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"age", "min_age", "max_age"}

    def test_string_concatenation(self):
        """Test variables in string concatenation."""
        template_source = "{{ first_name ~ ' ' ~ last_name }}"
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"first_name", "last_name"}

    def test_list_and_dict_access(self):
        """Test variables with subscript access."""
        template_source = "{{ items[0] }} and {{ data['key'] }}"
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"items", "data"}

    def test_ternary_expression(self):
        """Test variables in ternary expressions."""
        template_source = "{{ active_value if is_active else inactive_value }}"
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"active_value", "is_active", "inactive_value"}

    def test_loop_special_variables_not_required(self):
        """Test that loop special variables (loop.index, etc.) are not required."""
        template_source = """
        {% for item in items %}
            {{ loop.index }}: {{ item }}
        {% endfor %}
        """
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"items"}

    def test_unicode_variable_names(self):
        """Test detection with variable names containing unicode."""
        template_source = "{{ nom_français }} and {{ 日本語 }}"
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"nom_français", "日本語"}

    def test_underscore_variable_names(self):
        """Test detection with underscore-prefixed and suffixed variables."""
        template_source = "{{ _private }} and {{ __dunder__ }} and {{ normal_var }}"
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"_private", "__dunder__", "normal_var"}

    def test_full_paths_are_returned(self):
        """Test that full dotted paths are returned."""
        template_source = "{{ user.profile.name }} and {{ config.value }}"

        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == {"user.profile.name", "config.value"}

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.CHAINED_ACCESS,
    )
    def test_chained_access(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """An attribute on a subscript, a call or a filter keeps the read of the path it starts from."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.ASSIGNMENT_ORDER,
    )
    def test_assignment_order(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """A top-level `set` hides its name only from the statements after it."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.JINJA_SCOPE_RULES,
    )
    def test_jinja_scope_rules(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """A name the template sets is no input where Jinja binds it, and is the input of that name everywhere else."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.JINJA_SCOPE_RULES,
    )
    @pytest.mark.parametrize("is_truthy", [True, False])
    def test_jinja_reads_nothing_beyond_the_required_variables(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],  # ruff: ignore[unused-method-argument]
        is_truthy: bool,
    ):
        """Jinja itself renders each case with only the required roots in its context, so the walk never takes a read of the context for a local.

        Every root is given a value that answers any attribute or call with itself, and that is truthy and iterates once,
        or falsy and iterates not at all, so that both sides of every `if` and every loop's `else` run.
        """
        required = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        context = {get_root_from_dotted_path(path): _PermissiveValue(is_truthy=is_truthy) for path in required}
        template = Environment(undefined=PresenceProbingStrictUndefined).from_string(template_source)
        try:
            template.render(context)
        except UndefinedError as undefined_error:
            pytest.fail(f"{topic}: Jinja read '{undefined_error}' from the context, but the walk reported only {sorted(required)}")

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.SCOPES,
    )
    def test_scopes(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """Jinja's globals, a macro's internal names and a loop's own names are not required variables."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_variables"),
        TestData.GLOBAL_NAMES_AS_INPUTS,
    )
    def test_global_names_as_inputs(
        self,
        topic: str,
        template_source: str,
        expected_variables: set[str],
    ):
        """A read of a Jinja global's name that does not call it reads the input of that name, which shadows the global."""
        result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_variables, f"Failed for topic: {topic}"


class TestDetectJinja2VariableReferences:
    """Tests for detect_jinja2_variable_references function that tracks filters."""

    def test_simple_variable_no_filters(self) -> None:
        """Test simple variable without filters."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{{ name }}",
        )

        assert len(result) == 1
        assert result[0].path == "name"
        assert result[0].filters == []

    def test_variable_with_single_filter(self) -> None:
        """Test variable with a single filter applied."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source='{{ name|tag("name") }}',
        )

        assert len(result) == 1
        assert result[0].path == "name"
        assert "tag" in result[0].filters

    def test_variable_with_chained_filters(self) -> None:
        """Test variable with multiple chained filters."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{{ value|lower|upper|trim }}",
        )

        assert len(result) == 1
        assert result[0].path == "value"
        # All filters should be captured
        assert "lower" in result[0].filters
        assert "upper" in result[0].filters
        assert "trim" in result[0].filters

    def test_with_images_filter_detected(self) -> None:
        """Test that the with_images filter is detected."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{{ page | with_images }}",
        )

        assert len(result) == 1
        assert result[0].path == "page"
        assert "with_images" in result[0].filters

    def test_multiple_variables_different_filters(self) -> None:
        """Test multiple variables with different filters."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source='{{ name|tag("x") }} and {{ page | with_images }} and {{ plain }}',
        )

        assert len(result) == 3
        paths = {ref.path: ref.filters for ref in result}
        assert "tag" in paths["name"]
        assert "with_images" in paths["page"]
        assert paths["plain"] == []

    def test_nested_variable_with_filter(self) -> None:
        """Test nested dotted variable with filter."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{{ document.pages | with_images }}",
        )

        assert len(result) == 1
        assert result[0].path == "document.pages"
        assert "with_images" in result[0].filters

    def test_filter_arguments_not_in_filter_name(self) -> None:
        """Test that filter arguments don't affect the filter name."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source='{{ text|truncate(50)|default("N/A") }}',
        )

        assert len(result) == 1
        assert result[0].path == "text"
        assert "truncate" in result[0].filters
        assert "default" in result[0].filters
        # Arguments shouldn't be in filter names
        assert "50" not in result[0].filters
        assert "N/A" not in result[0].filters

    def test_same_variable_multiple_times_combines_filters(self) -> None:
        """Test that same variable referenced multiple times combines filters."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{{ name }} and {{ name|upper }}",
        )

        # Should have one entry for 'name' with the 'upper' filter
        assert len(result) == 1
        assert result[0].path == "name"
        assert "upper" in result[0].filters

    def test_format_filter_detected(self) -> None:
        """Test that format filter (common in MTHDS templates) is detected."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{{ content|format() }}",
        )

        assert len(result) == 1
        assert result[0].path == "content"
        assert "format" in result[0].filters

    def test_deeply_nested_path_with_filter(self) -> None:
        """Test deeply nested path with filter."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{{ document.section.pages.items | with_images }}",
        )

        assert len(result) == 1
        assert result[0].path == "document.section.pages.items"
        assert "with_images" in result[0].filters

    def test_for_loop_variable_not_included(self) -> None:
        """Test that for loop variables are not included as external references."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{% for item in items %}{{ item|upper }}{% endfor %}",
        )

        # Only 'items' should be returned, not 'item' (loop variable)
        assert len(result) == 1
        assert result[0].path == "items"

    def test_empty_template_returns_empty_list(self) -> None:
        """Test empty template returns empty list."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="No variables here",
        )

        assert result == []

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_paths"),
        TestData.REFERENCE_SCOPES + TestData.JINJA_SCOPE_RULES,
    )
    def test_scopes_match_required_variables(
        self,
        topic: str,
        template_source: str,
        expected_paths: set[str],
    ) -> None:
        """The references follow the same scopes as the required variables, so an input the check sees read is found here too."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert {reference.path for reference in result} == expected_paths, f"Failed for topic: {topic}"
        required = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert required == expected_paths, f"Failed for topic: {topic}"

    def test_loop_references_keep_source_order(self) -> None:
        """A loop's body is walked before its `else` branch, so references, and the images they attach, keep the template's order."""
        result = detect_jinja2_variable_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{% for x in xs %}{{ body_image }}{{ a|tag }}{% else %}{{ else_image }}{{ a|with_images }}{% endfor %}",
        )
        assert [reference.path for reference in result] == ["xs", "body_image", "a", "else_image"]
        assert result[2].filters == ["tag", "with_images"]
