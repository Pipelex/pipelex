from typing import ClassVar

import pytest

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import (
    detect_jinja2_required_variables,
    detect_jinja2_variable_references,
)


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
        topic: str,  # noqa: ARG002
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
