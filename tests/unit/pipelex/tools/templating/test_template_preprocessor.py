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
