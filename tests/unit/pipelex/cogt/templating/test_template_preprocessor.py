import pytest

from pipelex import pretty_print
from pipelex.cogt.templating.template_errors import TemplateSigilSyntaxError
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
        template = "@?optional\n@required"
        result = preprocess_template(template)
        expected = '{% if optional %}{{ optional|tag("optional") }}{% endif %}\n{{ required|tag("required") }}'
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
        """Test mixing @ patterns with numbers and valid variables.

        `@1.0` / `@?2.3.4` aren't candidate sigils (digit after `@`), so they pass through.
        The legitimate variables go on their own lines per the strict rule.
        """
        template = "Version @1.0, build @?2.3.4\n@valid_var\n@?optional_var"
        result = preprocess_template(template)
        expected = (
            'Version @1.0, build @?2.3.4\n{{ valid_var|tag("valid_var") }}\n{% if optional_var %}{{ optional_var|tag("optional_var") }}{% endif %}'
        )
        assert result == expected

    def test_dollar_variable_with_trailing_dot_in_sentence(self):
        """Inline $variable with trailing dot — $ keeps its inline contract."""
        template = "Extract employee information from this invoice text: $invoice_text."
        result = preprocess_template(template)
        expected = "Extract employee information from this invoice text: {{ invoice_text|format() }}."
        assert result == expected

    def test_multiple_dollar_variables_with_trailing_dots(self):
        """Inline $variable patterns with trailing dots — $ keeps its inline contract."""
        template = "Extract all articles from this invoice text: $invoice_text. Process the items: $item_list."
        result = preprocess_template(template)
        expected = "Extract all articles from this invoice text: {{ invoice_text|format() }}. Process the items: {{ item_list|format() }}."

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
        """Test real-world invoice extraction template.

        The block-shaped invoice body goes on its own line (`@invoice_text`); the inline
        company name uses `$company_name`.
        """
        template = """Extract employee information from this invoice text:
@invoice_text

The company name is: $company_name

Please extract the following fields:
- Employee name
- Employee ID
- Department

@?additional_instructions"""

        result = preprocess_template(template)
        expected = """Extract employee information from this invoice text:
{{ invoice_text|tag("invoice_text") }}

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

    def test_dollar_variable_followed_by_comma(self):
        """Inline $variable followed by comma — $ keeps its inline contract."""
        template = "Values: $first, $second, and $third"
        result = preprocess_template(template)
        expected = "Values: {{ first|format() }}, {{ second|format() }}, and {{ third|format() }}"
        assert result == expected

    def test_dollar_variable_followed_by_colon(self):
        """Inline $variable followed by colon."""
        template = "$label: the value is $value"
        result = preprocess_template(template)
        expected = "{{ label|format() }}: the value is {{ value|format() }}"
        assert result == expected

    def test_dollar_variable_followed_by_semicolon(self):
        """Inline $variable followed by semicolon."""
        template = "First: $first; Second: $second"
        result = preprocess_template(template)
        expected = "First: {{ first|format() }}; Second: {{ second|format() }}"
        assert result == expected

    def test_dollar_variable_in_brackets(self):
        """Inline $variable inside square brackets and surrounding context."""
        template = "Array element [$index] = $element"
        result = preprocess_template(template)
        expected = "Array element [{{ index|format() }}] = {{ element|format() }}"
        assert result == expected

    def test_dollar_variable_followed_by_question_mark(self):
        """Inline $variable followed by question mark."""
        template = "Is $value correct?"
        result = preprocess_template(template)
        expected = "Is {{ value|format() }} correct?"
        assert result == expected

    def test_dollar_variable_followed_by_exclamation(self):
        """Inline $variable followed by exclamation mark."""
        template = "Hello $name!"
        result = preprocess_template(template)
        expected = "Hello {{ name|format() }}!"
        assert result == expected

    # =========================================================================
    # Variables at different positions
    # =========================================================================

    def test_dollar_variable_at_start_of_line(self):
        """Inline $variable at the start of a line."""
        template = "$start_var is at the beginning"
        result = preprocess_template(template)
        expected = "{{ start_var|format() }} is at the beginning"
        assert result == expected

    def test_dollar_variable_at_end_of_line(self):
        """Inline $variable at the end of a line (no trailing punctuation)."""
        template = "The value is $end_var"
        result = preprocess_template(template)
        expected = "The value is {{ end_var|format() }}"
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

    def test_back_to_back_at_variables_alone_on_lines(self):
        """Multiple @ variables back to back on consecutive lines (each alone on line)."""
        template = "@first\n@second\n@third"
        result = preprocess_template(template)
        expected = '{{ first|tag("first") }}\n{{ second|tag("second") }}\n{{ third|tag("third") }}'
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

    def test_dollar_variable_with_leading_underscore(self):
        """Inline $variable names starting with underscore."""
        template = "$_private_var and $_another_private"
        result = preprocess_template(template)
        expected = "{{ _private_var|format() }} and {{ _another_private|format() }}"
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

    def test_all_pattern_types_across_lines(self):
        """Inline $ + line-bounded @ + line-bounded @? all in one template."""
        template = "$dollar_var\n@at_var\n@?optional_var"
        result = preprocess_template(template)
        expected = '{{ dollar_var|format() }}\n{{ at_var|tag("at_var") }}\n{% if optional_var %}{{ optional_var|tag("optional_var") }}{% endif %}'
        assert result == expected

    def test_nested_dollar_with_trailing_dot_in_complex_sentence(self):
        """Nested $variable with trailing dot in complex context."""
        template = "The user's preference is $user.settings.theme. Please apply it."
        result = preprocess_template(template)
        expected = "The user's preference is {{ user.settings.theme|format() }}. Please apply it."
        assert result == expected

    def test_dollar_variable_adjacent_to_newline(self):
        """Inline $variable immediately before newline."""
        template = "First: $first\nSecond: $second"
        result = preprocess_template(template)
        expected = "First: {{ first|format() }}\nSecond: {{ second|format() }}"
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
        """Multiple @? optional variables on consecutive lines (each alone on line)."""
        template = "@?first\n@?second\n@?third"
        result = preprocess_template(template)
        expected = (
            '{% if first %}{{ first|tag("first") }}{% endif %}\n'
            '{% if second %}{{ second|tag("second") }}{% endif %}\n'
            '{% if third %}{{ third|tag("third") }}{% endif %}'
        )
        assert result == expected

    # =========================================================================
    # Edge cases with @ symbol in non-variable contexts
    # =========================================================================

    def test_email_address_pass_through(self):
        """Email addresses must not be rewritten — the lookbehind on @ prevents it."""
        template = "Contact: someone@example.com"
        result = preprocess_template(template)
        assert result == template

    def test_at_sign_alone(self):
        """Test @ sign alone (not followed by valid variable name char)."""
        template = "Price @ store: $price"
        result = preprocess_template(template)
        expected = "Price @ store: {{ price|format() }}"
        assert result == expected

    def test_dollar_sign_alone(self):
        """Test $ sign alone (not followed by valid variable name char) with inline $variable."""
        template = "Cost is $ for $item"
        result = preprocess_template(template)
        expected = "Cost is $ for {{ item|format() }}"
        assert result == expected

    # =========================================================================
    # CSS at-rule strict-rule violations — each raises (escape with `@@` to opt out).
    # =========================================================================

    @pytest.mark.parametrize(
        ("template", "expected_sigil_and_identifier"),
        [
            ("@media (max-width: 820px) { color: red; }", "@media"),
            ("@supports (display: grid) { color: red; }", "@supports"),
            ('@import "reset.css";', "@import"),
            ('@import url("reset.css");', "@import"),
            ('@charset "UTF-8";', "@charset"),
            ('@namespace svg "http://www.w3.org/2000/svg";', "@namespace"),
            ("@keyframes spin { from { opacity: 0; } to { opacity: 1; } }", "@keyframes"),
            ("@page { margin: 1in; }", "@page"),
            ("@layer reset { color: red; }", "@layer"),
            ("@container (width > 400px) { color: red; }", "@container"),
            ('@font-face { font-family: "X"; }', "@font"),
        ],
        ids=[
            "media",
            "supports",
            "import_string",
            "import_url",
            "charset",
            "namespace",
            "keyframes",
            "page",
            "layer_named",
            "container",
            "font_face",
        ],
    )
    def test_css_at_rule_raises_under_strict_rule(self, template: str, expected_sigil_and_identifier: str):
        """CSS at-rules are inline `@` candidates — they violate the strict line-bounded rule
        and raise. Authors escape with `@@` to opt out (see companion `*_escaped_pass_through`
        tests).
        """
        with pytest.raises(TemplateSigilSyntaxError) as exc_info:
            preprocess_template(template)
        error_message = str(exc_info.value)
        assert "line 1" in error_message
        assert expected_sigil_and_identifier in error_message

    def test_css_namespace_escaped_pass_through(self):
        """Author workaround for @namespace: escape with @@namespace."""
        template = '@@namespace svg "http://www.w3.org/2000/svg";'
        result = preprocess_template(template)
        expected = '@namespace svg "http://www.w3.org/2000/svg";'
        assert result == expected

    def test_css_font_face_escaped_pass_through(self):
        """Author workaround for @font-face: escape with @@font-face."""
        template = '@@font-face { font-family: "X"; }'
        result = preprocess_template(template)
        expected = '@font-face { font-family: "X"; }'
        assert result == expected

    def test_full_style_block_raises_under_strict_rule(self):
        """Under the strict line-bounded `@` rule, a realistic <style> block raises
        TemplateSigilSyntaxError on the first inline at-rule (no longer pass-through).
        """
        template = """<style>
  .page { padding: 32px; }
  @media (max-width: 820px) {
    .page { padding: 24px; }
  }
  @supports (display: grid) {
    .grid { display: grid; }
  }
</style>"""
        with pytest.raises(TemplateSigilSyntaxError) as exc_info:
            preprocess_template(template)
        error_message = str(exc_info.value)
        assert "line 3" in error_message
        assert "@media" in error_message
        assert "@@" in error_message  # escape hint must be present

    def test_full_style_block_escaped_pass_through(self):
        """Authors escape every CSS at-rule in a <style> block with `@@` to opt out of
        strict-rule enforcement; the doubled sigils restore to literal `@` and nothing
        is rewritten as a Pipelex sigil.
        """
        template = """<style>
  .page { padding: 32px; }
  @@media (max-width: 820px) {
    .page { padding: 24px; }
  }
  @@supports (display: grid) {
    .grid { display: grid; }
  }
</style>"""
        expected = """<style>
  .page { padding: 32px; }
  @media (max-width: 820px) {
    .page { padding: 24px; }
  }
  @supports (display: grid) {
    .grid { display: grid; }
  }
</style>"""
        assert preprocess_template(template) == expected

    # =========================================================================
    # Email / word-adjacent @ pass-through (heuristic lookbehind)
    # =========================================================================

    def test_email_in_sentence_pass_through(self):
        """Email address embedded in a sentence must not be rewritten."""
        template = "Contact us at hello@pipelex.com for help."
        result = preprocess_template(template)
        assert result == template

    def test_word_adjacent_at_pass_through(self):
        """@ preceded by a word character (email-like) must not be rewritten."""
        template = "Send to noreply@anthropic.com immediately."
        result = preprocess_template(template)
        assert result == template

    # =========================================================================
    # Code-like punctuation regression guards (already pass today, locked in by lookahead)
    # =========================================================================

    def test_jquery_call_pass_through(self):
        """jQuery-style $("...") call must not be rewritten."""
        template = '$("body").addClass("x")'
        result = preprocess_template(template)
        assert result == template

    def test_bash_subshell_pass_through(self):
        """Bash subshell $(...) must not be rewritten."""
        template = "result=$(date +%s)"
        result = preprocess_template(template)
        assert result == template

    def test_dollar_brace_pass_through(self):
        """Shell ${VAR} must not be rewritten."""
        template = "Use ${PATH} for the path."
        result = preprocess_template(template)
        assert result == template

    # =========================================================================
    # Escape sequences: @@ → literal @, $$ → literal $
    # =========================================================================

    def test_double_at_escapes_to_literal_at(self):
        """@@media must collapse to literal @media with no interpolation."""
        template = "@@media (max-width: 820px) { color: red; }"
        result = preprocess_template(template)
        expected = "@media (max-width: 820px) { color: red; }"
        assert result == expected

    def test_double_at_makes_at_var_literal(self):
        """@@var must collapse to literal @var (no {{ ... }} interpolation)."""
        template = "Use @@var here."
        result = preprocess_template(template)
        expected = "Use @var here."
        assert result == expected

    def test_double_dollar_escapes_to_literal_dollar(self):
        """$$10 must collapse to literal $10."""
        template = "Cost is $$10."
        result = preprocess_template(template)
        expected = "Cost is $10."
        assert result == expected

    def test_double_dollar_makes_dollar_var_literal(self):
        """$$var must collapse to literal $var (no interpolation)."""
        template = "Use $$var here."
        result = preprocess_template(template)
        expected = "Use $var here."
        assert result == expected

    def test_escape_does_not_consume_legit_variable(self):
        """Escape on one token must not affect a legitimate variable later in the string."""
        template = "@@media is literal, but $width is a variable."
        result = preprocess_template(template)
        expected = "@media is literal, but {{ width|format() }} is a variable."
        assert result == expected

    def test_triple_at_raises_under_strict_rule(self):
        """`@@@var` post-sentinel becomes literal `@` + `@var`; the `@var` is no longer alone
        on its line (the sentinel-substituted `@` sits in front of it), so the strict rule
        raises. Authors who want literal `@` followed by an interpolated `@var` must move the
        variable onto its own line.
        """
        template = "@@@var"
        with pytest.raises(TemplateSigilSyntaxError) as exc_info:
            preprocess_template(template)
        error_message = str(exc_info.value)
        assert "@var" in error_message
        assert "line 1" in error_message

    def test_quadruple_at_is_two_escapes(self):
        """@@@@var → @@var — two non-overlapping escapes, no interpolation."""
        template = "@@@@var"
        result = preprocess_template(template)
        expected = "@@var"
        assert result == expected

    def test_escape_inside_style_block(self):
        """@@font-face inside a <style> block restores to literal @font-face."""
        template = '<style>@@font-face { font-family: "X"; }</style>'
        result = preprocess_template(template)
        expected = '<style>@font-face { font-family: "X"; }</style>'
        assert result == expected

    # =========================================================================
    # Broader CSS class (hyphenated names / dash arguments): each raises under the
    # strict line-bounded `@` rule; authors escape with `@@`.
    # =========================================================================

    @pytest.mark.parametrize(
        ("template", "expected_sigil_and_identifier"),
        [
            ("@property --my-color { syntax: '<color>'; inherits: false; }", "@property"),
            ("@counter-style thumbs { system: cyclic; }", "@counter"),
            ("@color-profile --swop5c { src: url('x.icc'); }", "@color"),
            ("@view-transition { navigation: auto; }", "@view"),
        ],
        ids=["property", "counter-style", "color-profile", "view-transition"],
    )
    def test_css_dash_at_rule_raises_under_strict_rule(self, template: str, expected_sigil_and_identifier: str):
        """At-rules with hyphenated names or dash arguments now raise under the strict rule.
        The validator captures only the leading `@` + identifier (it stops at the hyphen
        boundary, just like the rewriter did before), but the diagnostic still names the
        right line and migration hint.
        """
        with pytest.raises(TemplateSigilSyntaxError) as exc_info:
            preprocess_template(template)
        error_message = str(exc_info.value)
        assert "line 1" in error_message
        assert expected_sigil_and_identifier in error_message

    def test_css_dash_at_rule_escape_workaround(self):
        """`@@property --my-color { ... }` proves the documented workaround for the
        hyphenated/dash-arg CSS class.
        """
        template = "@@property --my-color { syntax: '<color>'; inherits: false; }"
        result = preprocess_template(template)
        expected = "@property --my-color { syntax: '<color>'; inherits: false; }"
        assert result == expected

    # =========================================================================
    # Strict line-bounded `@` sigil contract — alone-on-line success cases
    # (Phase 2 contract: `@var` and `@?var` are valid only when alone on their line.
    # Leading and trailing whitespace is preserved through the rewrite so templates
    # embedded in indented YAML/TOML blocks survive a round-trip.)
    # =========================================================================

    @pytest.mark.parametrize(
        ("template", "expected"),
        [
            ("@var", '{{ var|tag("var") }}'),
            ("@?var", '{% if var %}{{ var|tag("var") }}{% endif %}'),
            ("@user.profile.bio", '{{ user.profile.bio|tag("user.profile.bio") }}'),
            ("@_private_var", '{{ _private_var|tag("_private_var") }}'),
            ("    @indented_var", '    {{ indented_var|tag("indented_var") }}'),
            ("@var\t", '{{ var|tag("var") }}\t'),
            (
                "\t@?indented_optional",
                '\t{% if indented_optional %}{{ indented_optional|tag("indented_optional") }}{% endif %}',
            ),
            (
                "Line before\n    @middle\nLine after",
                'Line before\n    {{ middle|tag("middle") }}\nLine after',
            ),
        ],
        ids=[
            "bare_at_var",
            "bare_optional_at_var",
            "dotted_at_var",
            "underscore_prefixed_at_var",
            "indented_at_var",
            "trailing_tab_at_var",
            "tab_indented_optional_at_var",
            "indented_at_var_in_block",
        ],
    )
    def test_strict_line_at_sigil_success(self, template: str, expected: str):
        """Alone-on-line @ / @? sigils (with optional leading/trailing whitespace)
        rewrite correctly; whitespace is preserved.
        """
        assert preprocess_template(template) == expected

    @pytest.mark.parametrize(
        ("template", "expected"),
        [
            (
                "Header\r\n@payload\r\nFooter",
                'Header\n{{ payload|tag("payload") }}\nFooter',
            ),
            (
                "@only_var\r\n",
                '{{ only_var|tag("only_var") }}\n',
            ),
            (
                "Old Mac\r@payload\rEnd",
                'Old Mac\n{{ payload|tag("payload") }}\nEnd',
            ),
        ],
        ids=["crlf_surrounded", "crlf_terminated", "cr_only_old_mac"],
    )
    def test_strict_line_at_sigil_handles_crlf_and_cr_line_endings(self, template: str, expected: str):
        r"""Lines terminated with `\r\n` (Windows) or `\r` (classic Mac) must not be misread as
        inline candidates. Line endings are normalized to `\n` at the top of the preprocessor,
        so the alone-on-line sigil rewrites correctly and the validator does not raise. The
        normalized `\n`-only output is what downstream Jinja rendering sees.
        """
        assert preprocess_template(template) == expected

    # =========================================================================
    # Strict line-bounded `@` sigil contract — error cases (raises)
    # =========================================================================

    @pytest.mark.parametrize(
        ("template", "expected_line", "expected_sigil", "expected_identifier"),
        [
            # Inline mid-sentence
            ("Extract from @invoice_text. Done.", 1, "@", "invoice_text"),
            # Inline trailing punctuation
            ("@var.", 1, "@", "var"),
            ("@var,", 1, "@", "var"),
            ("@var!", 1, "@", "var"),
            ("@var?", 1, "@", "var"),
            ("@var;", 1, "@", "var"),
            ("@var:", 1, "@", "var"),
            # Inline parenthetical / bracketed
            ("(@var)", 1, "@", "var"),
            ("[@var]", 1, "@", "var"),
            # Multiple sigils per line
            ("@a @b", 1, "@", "a"),
            ("@a $b", 1, "@", "a"),
            ("$b @a", 1, "@", "a"),
            # Word-adjacent (space before — not email)
            ("Word @var", 1, "@", "var"),
            ("@var Word", 1, "@", "var"),
            # Optional sigil inline
            ("Hello @?notes", 1, "@?", "notes"),
            # CSS at-rules — no longer pass-through
            ("@media (max-width: 820px) {", 1, "@", "media"),
            ('@font-face { font-family: "X"; }', 1, "@", "font"),
            ('@import url("reset.css");', 1, "@", "import"),
            ("@keyframes spin { from { opacity: 0; } }", 1, "@", "keyframes"),
            # Code constructs (`@Override` alone on its line IS a valid sigil — authors who want
            # a literal Java/Python decorator must escape with `@@Override`. Only the inline
            # shape `@deprecated def foo():` raises.)
            ("@deprecated def foo():", 1, "@", "deprecated"),
            # Multi-line: first error reported, with correct 1-based line number
            ("OK line\nbroken @var line\nanother line", 2, "@", "var"),
        ],
    )
    def test_strict_line_at_sigil_raises(
        self,
        template: str,
        expected_line: int,
        expected_sigil: str,
        expected_identifier: str,
    ):
        """Inline / non-alone @ or @? sigils raise TemplateSigilSyntaxError with a
        message that names the line, the offending span, and a migration hint.
        """
        with pytest.raises(TemplateSigilSyntaxError) as exc_info:
            preprocess_template(template)
        error_message = str(exc_info.value)
        offending_span = f"{expected_sigil}{expected_identifier}"
        # Line number must be present and correctly 1-based
        assert f"line {expected_line}" in error_message
        # Offending span (sigil + identifier) must be quoted somewhere in the message
        assert offending_span in error_message
        # Migration hints — both alternatives must be visible to the author
        assert f"${expected_identifier}" in error_message  # inline-value migration
        assert "@@" in error_message  # literal-escape hint

    # =========================================================================
    # Word-adjacent `@` is not a candidate sigil — silent pass-through
    # =========================================================================

    @pytest.mark.parametrize(
        "template",
        [
            "someone@example.com",
            "hello@pipelex.com",
            "Send to noreply@anthropic.com immediately.",
            "prefix@suffix",
            "Contact us at hello@pipelex.com for help.",
        ],
        ids=[
            "bare_email",
            "domain_email",
            "email_in_sentence",
            "letters_around_at",
            "email_in_help_sentence",
        ],
    )
    def test_word_adjacent_at_silent_pass_through(self, template: str):
        """`@` preceded by a word character (emails, prose hashtags) is not a candidate
        sigil and passes through silently — never raises, never rewrites.
        """
        assert preprocess_template(template) == template
