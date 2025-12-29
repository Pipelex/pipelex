from typing import ClassVar

import pytest

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_errors import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import (
    detect_jinja2_full_variable_paths,
    detect_jinja2_required_variables,
)


class TestData:
    """Test data for detect_jinja2_required_variables tests."""

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
        ("simple_dot_notation", "{{ user.name }}", {"user"}),
        ("deep_nesting", "{{ user.profile.bio.short }}", {"user"}),
        ("multiple_nested", "{{ user.name }} and {{ config.setting }}", {"user", "config"}),
        (
            "mix_nested_and_simple",
            "Hello {{ name }}, your email is {{ user.email }}",
            {"name", "user"},
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
            {"recipient", "greeting", "topic", "action_items", "sender"},
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
            {"user"},
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


class TestDetectJinja2RequiredVariables:
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
        """Test detection of nested/dotted variables (only root is detected)."""
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


class TestDataFullPaths:
    """Test data for detect_jinja2_full_variable_paths tests.

    Note: This function returns ONLY the leaf (full) paths, not intermediate paths.
    For example, `{{ foo.bar.baz }}` returns `{"foo.bar.baz"}`, NOT `{"foo", "foo.bar", "foo.bar.baz"}`.
    """

    SIMPLE_VARIABLES: ClassVar[list[tuple[str, str, set[str]]]] = [
        ("single_variable", "Hello {{ name }}", {"name"}),
        ("two_variables", "{{ first }} and {{ second }}", {"first", "second"}),
        ("empty_template", "No variables here", set()),
    ]

    NESTED_VARIABLES: ClassVar[list[tuple[str, str, set[str]]]] = [
        # Only the full path is returned, not intermediate paths
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

    PLX_STYLE_TEMPLATES: ClassVar[list[tuple[str, str, set[str]]]] = [
        (
            "plx_at_variable_preprocessed",
            '{{ page.page_view|tag("page.page_view") }}',
            {"page.page_view"},
        ),
        (
            "plx_dollar_variable_preprocessed",
            "{{ page.text_and_images.text.text|format() }}",
            {"page.text_and_images.text.text"},
        ),
        (
            "plx_mixed_preprocessed",
            '{{ page.page_view|tag("page.page_view") }}\n{{ page.text_and_images.text.text|format() }}',
            {"page.page_view", "page.text_and_images.text.text"},
        ),
    ]

    CONTROL_STRUCTURES: ClassVar[list[tuple[str, str, set[str]]]] = [
        (
            "for_loop_item_excluded",
            "{% for item in items %}{{ item.name }}{% endfor %}",
            {"items"},  # 'item' is loop variable, 'item.name' should not be detected
        ),
        (
            "for_loop_with_external_var",
            "{% for item in items %}{{ item.name }} ({{ prefix.value }}){% endfor %}",
            {"items", "prefix.value"},
        ),
    ]


class TestDetectJinja2FullVariablePaths:
    """Tests for detect_jinja2_full_variable_paths function."""

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_paths"),
        TestDataFullPaths.SIMPLE_VARIABLES,
    )
    def test_simple_variables(
        self,
        topic: str,
        template_source: str,
        expected_paths: set[str],
    ):
        """Test detection of simple variables returns full paths."""
        result = detect_jinja2_full_variable_paths(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_paths, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_paths"),
        TestDataFullPaths.NESTED_VARIABLES,
    )
    def test_nested_variables(
        self,
        topic: str,
        template_source: str,
        expected_paths: set[str],
    ):
        """Test detection of nested variables returns all full dotted paths."""
        result = detect_jinja2_full_variable_paths(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_paths, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_paths"),
        TestDataFullPaths.PLX_STYLE_TEMPLATES,
    )
    def test_plx_style_templates(
        self,
        topic: str,
        template_source: str,
        expected_paths: set[str],
    ):
        """Test detection in PLX-style preprocessed templates with tag/format filters."""
        result = detect_jinja2_full_variable_paths(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_paths, f"Failed for topic: {topic}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_paths"),
        TestDataFullPaths.CONTROL_STRUCTURES,
    )
    def test_control_structures(
        self,
        topic: str,
        template_source: str,
        expected_paths: set[str],
    ):
        """Test that loop variables and set variables are properly excluded."""
        result = detect_jinja2_full_variable_paths(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert result == expected_paths, f"Failed for topic: {topic}"

    def test_empty_template(self):
        """Test that empty template returns empty set."""
        result = detect_jinja2_full_variable_paths(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="",
        )
        assert result == set()

    def test_comparison_with_root_only_detection(self):
        """Test that full path detection differs from root-only detection."""
        template_source = "{{ user.profile.name }}"

        # Root-only detection returns just the root variable name
        root_result = detect_jinja2_required_variables(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert root_result == {"user"}, "Root-only should return just 'user'"

        # Full path detection returns ONLY the complete path (not intermediate paths)
        full_result = detect_jinja2_full_variable_paths(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
        )
        assert full_result == {"user.profile.name"}, "Full paths should return only the complete path"
