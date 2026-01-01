from pipelex import pretty_print
from pipelex.cogt.templating.template_preprocessor import preprocess_template


class TestTemplatePreprocessor:
    def test_at_variable_pattern(self):
        """Test basic @variable pattern replacement."""
        template = "@expense\n@invoices"
        result = preprocess_template(template)
        expected = '{{ expense|tag("expense") }}\n{{ invoices|tag("invoices") }}'
        assert result == expected

    def test_dollar_variable_pattern(self):
        """Test basic $variable pattern replacement."""
        template = "Your goal is to summarize everything related to $topic"
        result = preprocess_template(template)
        expected = "Your goal is to summarize everything related to {{ topic|format() }}"
        assert result == expected

    def test_dollar_variable_with_trailing_dot(self):
        """Test $variable pattern with trailing dot."""
        template = "The value is $amount."
        result = preprocess_template(template)
        expected = "The value is {{ amount|format() }}."
        assert result == expected

    def test_optional_at_variable_pattern(self):
        """Test @?variable pattern for optional insertion."""
        template = "Here is the data:\n@?optional_field\nEnd of data."
        result = preprocess_template(template)
        expected = 'Here is the data:\n{% if optional_field %}{{ optional_field|tag("optional_field") }}{% endif %}\nEnd of data.'
        assert result == expected

    def test_optional_at_variable_with_dots(self):
        """Test @?variable pattern with dots in variable name."""
        template = "@?user.profile.bio"
        result = preprocess_template(template)
        expected = '{% if user.profile.bio %}{{ user.profile.bio|tag("user.profile.bio") }}{% endif %}'
        assert result == expected

    def test_mixed_patterns(self):
        """Test mixing all patterns: @?, @, and $."""
        template = """Summary for $name:

@?description

@details

Optional notes:
@?notes"""
        result = preprocess_template(template)
        expected = """Summary for {{ name|format() }}:

{% if description %}{{ description|tag("description") }}{% endif %}

{{ details|tag("details") }}

Optional notes:
{% if notes %}{{ notes|tag("notes") }}{% endif %}"""
        assert result == expected

    def test_no_replacement_needed(self):
        """Test template with no special patterns."""
        template = "This is a plain template with no special syntax."
        result = preprocess_template(template)
        assert result == template

    def test_complex_variable_names(self):
        """Test patterns with complex variable names."""
        template = "@item_1\n$price_2\n@?metadata_3"
        result = preprocess_template(template)
        expected = '{{ item_1|tag("item_1") }}\n{{ price_2|format() }}\n{% if metadata_3 %}{{ metadata_3|tag("metadata_3") }}{% endif %}'
        assert result == expected

    def test_optional_pattern_priority(self):
        """Test that @? pattern is processed before @ pattern."""
        # This ensures @? doesn't get matched as @ followed by ?
        template = "@?optional @required"
        result = preprocess_template(template)
        expected = '{% if optional %}{{ optional|tag("optional") }}{% endif %} {{ required|tag("required") }}'
        assert result == expected

    def test_dollar_amounts_not_processed(self):
        """Test that dollar amounts are not processed as variables."""
        template = "The price is $10M and the budget is $1000.50"
        result = preprocess_template(template)
        assert result == template

    def test_mixed_dollar_amounts_and_variables(self):
        """Test mixing dollar amounts with dollar variables."""
        template = "The price is $10M and the budget is $budget_amount"
        result = preprocess_template(template)
        expected = "The price is $10M and the budget is {{ budget_amount|format() }}"
        assert result == expected

    def test_dollar_amounts_with_spaces(self):
        """Test dollar amounts with spaces after the dollar sign."""
        template = "The price is $ 10M and the budget is $ 1000.50"
        result = preprocess_template(template)
        assert result == template

    def test_at_with_numbers_not_processed(self):
        """Test that @ patterns followed by numbers are not processed."""
        template = "The version is @1.0 and the build is @2.3.4"
        result = preprocess_template(template)
        assert result == template

    def test_optional_at_with_numbers_not_processed(self):
        """Test that @? patterns followed by numbers are not processed."""
        template = "The version is @?1.0 and the build is @?2.3.4"
        result = preprocess_template(template)
        assert result == template

    def test_mixed_at_patterns_with_numbers(self):
        """Test mixing @ patterns with numbers and valid variables."""
        template = "Version @1.0, build @?2.3.4, and @valid_var with @?optional_var"
        result = preprocess_template(template)
        expected = (
            "Version @1.0, build @?2.3.4, and "
            '{{ valid_var|tag("valid_var") }} with '
            '{% if optional_var %}{{ optional_var|tag("optional_var") }}{% endif %}'
        )
        assert result == expected

    def test_at_variable_with_trailing_dot(self):
        """Test @variable pattern with trailing dot (punctuation)."""
        template = "Extract employee information from this invoice text: @invoice_text."
        result = preprocess_template(template)
        expected = 'Extract employee information from this invoice text: {{ invoice_text|tag("invoice_text") }}.'
        assert result == expected

    def test_optional_at_variable_with_trailing_dot(self):
        """Test @?variable pattern with trailing dot (punctuation)."""
        template = "Optional information: @?optional_data."
        result = preprocess_template(template)
        expected = 'Optional information: {% if optional_data %}{{ optional_data|tag("optional_data") }}{% endif %}.'
        assert result == expected

    def test_multiple_at_variables_with_trailing_dots(self):
        """Test multiple @variable patterns with trailing dots."""
        template = "Extract all articles from this invoice text: @invoice_text. Process the items: @item_list."
        result = preprocess_template(template)
        expected = """Extract all articles from this invoice text: {{ invoice_text|tag("invoice_text") }}. Process the items: {{ item_list|tag("item_list") }}."""  # noqa: E501

        pretty_print(result, title="result")
        pretty_print(expected, title="expected")
        assert result == expected

    # =========================================================================
    # Real-world template tests
    # =========================================================================

    def test_gantt_chart_analysis_template(self):
        """Test real-world Gantt chart analysis template."""
        template = """I am sharing an image of a Gantt chart: $gantt_chart_image.
Please analyse the image and for a given task name (and only this task), extract the information of the task, if relevant.

Be careful, the time unit is this:
@gantt_timescale

If the task is a milestone, then only output the start_date.

Here is the name of the task you have to extract the dates for:
@gantt_task_name"""

        result = preprocess_template(template)
        expected = """I am sharing an image of a Gantt chart: {{ gantt_chart_image|format() }}.
Please analyse the image and for a given task name (and only this task), extract the information of the task, if relevant.

Be careful, the time unit is this:
{{ gantt_timescale|tag("gantt_timescale") }}

If the task is a milestone, then only output the start_date.

Here is the name of the task you have to extract the dates for:
{{ gantt_task_name|tag("gantt_task_name") }}"""

        assert result == expected

    def test_invoice_extraction_template(self):
        """Test real-world invoice extraction template."""
        template = """Extract employee information from this invoice text: @invoice_text.

The company name is: $company_name

Please extract the following fields:
- Employee name
- Employee ID
- Department

@?additional_instructions"""

        result = preprocess_template(template)
        expected = """Extract employee information from this invoice text: {{ invoice_text|tag("invoice_text") }}.

The company name is: {{ company_name|format() }}

Please extract the following fields:
- Employee name
- Employee ID
- Department

{% if additional_instructions %}{{ additional_instructions|tag("additional_instructions") }}{% endif %}"""

        assert result == expected

    # =========================================================================
    # Edge cases with punctuation and special characters
    # =========================================================================

    def test_variable_followed_by_comma(self):
        """Test variable followed by comma."""
        template = "Values: @first, @second, and @third"
        result = preprocess_template(template)
        expected = 'Values: {{ first|tag("first") }}, {{ second|tag("second") }}, and {{ third|tag("third") }}'
        assert result == expected

    def test_variable_followed_by_colon(self):
        """Test variable followed by colon."""
        template = "@label: the value is @value"
        result = preprocess_template(template)
        expected = '{{ label|tag("label") }}: the value is {{ value|tag("value") }}'
        assert result == expected

    def test_variable_followed_by_semicolon(self):
        """Test variable followed by semicolon."""
        template = "First: @first; Second: @second"
        result = preprocess_template(template)
        expected = 'First: {{ first|tag("first") }}; Second: {{ second|tag("second") }}'
        assert result == expected

    def test_variable_in_parentheses(self):
        """Test variable inside parentheses."""
        template = "The value (@value) is important"
        result = preprocess_template(template)
        expected = 'The value ({{ value|tag("value") }}) is important'
        assert result == expected

    def test_variable_in_brackets(self):
        """Test variable inside square brackets."""
        template = "Array element [$index] = @element"
        result = preprocess_template(template)
        expected = 'Array element [{{ index|format() }}] = {{ element|tag("element") }}'
        assert result == expected

    def test_variable_followed_by_question_mark(self):
        """Test variable followed by question mark (but not @? pattern)."""
        template = "Is @value correct?"
        result = preprocess_template(template)
        expected = 'Is {{ value|tag("value") }} correct?'
        assert result == expected

    def test_variable_followed_by_exclamation(self):
        """Test variable followed by exclamation mark."""
        template = "Hello @name!"
        result = preprocess_template(template)
        expected = 'Hello {{ name|tag("name") }}!'
        assert result == expected

    # =========================================================================
    # Variables at different positions
    # =========================================================================

    def test_variable_at_start_of_line(self):
        """Test variable at the start of a line."""
        template = "@start_var is at the beginning"
        result = preprocess_template(template)
        expected = '{{ start_var|tag("start_var") }} is at the beginning'
        assert result == expected

    def test_variable_at_end_of_line(self):
        """Test variable at the end of a line (no trailing punctuation)."""
        template = "The value is @end_var"
        result = preprocess_template(template)
        expected = 'The value is {{ end_var|tag("end_var") }}'
        assert result == expected

    def test_variable_alone_on_line(self):
        """Test variable alone on its own line."""
        template = """Line before
@alone_var
Line after"""
        result = preprocess_template(template)
        expected = """Line before
{{ alone_var|tag("alone_var") }}
Line after"""
        assert result == expected

    def test_back_to_back_at_variables(self):
        """Test multiple @ variables back to back with space."""
        template = "@first @second @third"
        result = preprocess_template(template)
        expected = '{{ first|tag("first") }} {{ second|tag("second") }} {{ third|tag("third") }}'
        assert result == expected

    def test_back_to_back_dollar_variables(self):
        """Test multiple $ variables back to back with space."""
        template = "$first $second $third"
        result = preprocess_template(template)
        expected = "{{ first|format() }} {{ second|format() }} {{ third|format() }}"
        assert result == expected

    # =========================================================================
    # Complex nested variable names
    # =========================================================================

    def test_deeply_nested_at_variable(self):
        """Test deeply nested @ variable with multiple dots."""
        template = "@user.profile.settings.preferences.theme"
        result = preprocess_template(template)
        expected = '{{ user.profile.settings.preferences.theme|tag("user.profile.settings.preferences.theme") }}'
        assert result == expected

    def test_deeply_nested_dollar_variable(self):
        """Test deeply nested $ variable with multiple dots."""
        template = "$config.database.connection.pool.size"
        result = preprocess_template(template)
        expected = "{{ config.database.connection.pool.size|format() }}"
        assert result == expected

    def test_deeply_nested_optional_variable(self):
        """Test deeply nested @? optional variable."""
        template = "@?system.logs.archive.entries"
        result = preprocess_template(template)
        expected = '{% if system.logs.archive.entries %}{{ system.logs.archive.entries|tag("system.logs.archive.entries") }}{% endif %}'
        assert result == expected

    # =========================================================================
    # Variable names with underscores
    # =========================================================================

    def test_variable_with_leading_underscore(self):
        """Test variable name starting with underscore."""
        template = "@_private_var and $_another_private"
        result = preprocess_template(template)
        expected = '{{ _private_var|tag("_private_var") }} and {{ _another_private|format() }}'
        assert result == expected

    def test_variable_with_multiple_underscores(self):
        """Test variable name with multiple consecutive underscores."""
        template = "@snake__case__var"
        result = preprocess_template(template)
        expected = '{{ snake__case__var|tag("snake__case__var") }}'
        assert result == expected

    def test_variable_ending_with_underscore(self):
        """Test variable name ending with underscore."""
        template = "@trailing_"
        result = preprocess_template(template)
        expected = '{{ trailing_|tag("trailing_") }}'
        assert result == expected

    # =========================================================================
    # Mixed scenarios
    # =========================================================================

    def test_all_pattern_types_in_one_line(self):
        """Test all three pattern types in a single line."""
        template = "$dollar_var @at_var @?optional_var"
        result = preprocess_template(template)
        expected = '{{ dollar_var|format() }} {{ at_var|tag("at_var") }} {% if optional_var %}{{ optional_var|tag("optional_var") }}{% endif %}'
        assert result == expected

    def test_nested_with_trailing_dot_in_complex_sentence(self):
        """Test nested variable with trailing dot in complex context."""
        template = "The user's preference is @user.settings.theme. Please apply it."
        result = preprocess_template(template)
        expected = 'The user\'s preference is {{ user.settings.theme|tag("user.settings.theme") }}. Please apply it.'
        assert result == expected

    def test_variable_adjacent_to_newline(self):
        """Test variable immediately before newline."""
        template = "First: @first\nSecond: @second"
        result = preprocess_template(template)
        expected = 'First: {{ first|tag("first") }}\nSecond: {{ second|tag("second") }}'
        assert result == expected

    def test_empty_template(self):
        """Test empty template string."""
        template = ""
        result = preprocess_template(template)
        assert result == ""

    def test_whitespace_only_template(self):
        """Test template with only whitespace."""
        template = "   \n\t\n   "
        result = preprocess_template(template)
        assert result == template

    def test_template_with_existing_jinja2_syntax(self):
        """Test that existing Jinja2 syntax is preserved."""
        template = "Hello {{ existing_var }}, your topic is $topic"
        result = preprocess_template(template)
        expected = "Hello {{ existing_var }}, your topic is {{ topic|format() }}"
        assert result == expected

    def test_multiple_optional_variables_in_sequence(self):
        """Test multiple optional variables in sequence."""
        template = "@?first @?second @?third"
        result = preprocess_template(template)
        expected = (
            '{% if first %}{{ first|tag("first") }}{% endif %} '
            '{% if second %}{{ second|tag("second") }}{% endif %} '
            '{% if third %}{{ third|tag("third") }}{% endif %}'
        )
        assert result == expected

    # =========================================================================
    # Edge cases with @ symbol in non-variable contexts
    # =========================================================================

    def test_email_address_partially_processed(self):
        """Test that email-like patterns are partially processed (after @).

        The regex pattern [a-zA-Z0-9_.] matches 'example.com' as a single variable
        name since dots are allowed in variable names.
        """
        # Note: user@domain.ext will match 'domain.ext' as variable after @
        template = "Contact: someone@example.com"
        result = preprocess_template(template)
        # After @ we have example.com which matches entirely as variable name
        expected = 'Contact: someone{{ example.com|tag("example.com") }}'
        assert result == expected

    def test_at_sign_alone(self):
        """Test @ sign alone (not followed by valid variable name char)."""
        template = "Price @ store: $price"
        result = preprocess_template(template)
        expected = "Price @ store: {{ price|format() }}"
        assert result == expected

    def test_dollar_sign_alone(self):
        """Test $ sign alone (not followed by valid variable name char)."""
        template = "Cost is $ for @item"
        result = preprocess_template(template)
        expected = 'Cost is $ for {{ item|tag("item") }}'
        assert result == expected
