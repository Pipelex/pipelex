"""Guard classification for declared-optional template variables (D7): every reference to an
optional input must be guarded — reachable only inside `{% if var %}`-style blocks, inline
`is defined` conditionals, or via `@?var` (whose rewritten form is a `{% if %}` guard). The
walker reports each unguarded reference so validation can name the precise fix.
"""

import pytest

from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.tools.jinja2.jinja2_optional_guards import detect_unguarded_optional_references


class TestDetectUnguardedOptionalReferences:
    @pytest.mark.parametrize(
        ("topic", "template_source"),
        [
            ("if_block_guard", "{% if assessment %}{{ assessment.amount }}{% endif %}"),
            ("if_defined_guard", "{% if assessment is defined %}{{ assessment }}{% endif %}"),
            ("at_optional_rewritten_form", '{% if assessment %}{{ assessment|tag("assessment") }}{% endif %}'),
            ("inline_cond_defined", "{{ 'has assessment' if assessment is defined else 'none' }}"),
            ("inline_cond_truthy", "{{ assessment.amount if assessment else 'none' }}"),
            ("and_guard", "{% if assessment and topic %}{{ assessment.amount }}{% endif %}"),
            ("bare_presence_test_only", "{% if assessment %}present{% endif %}"),
            ("nested_guard", "{% if assessment %}{% for item in assessment.items %}{{ item }}{% endfor %}{% endif %}"),
            ("non_optional_vars_untouched", "{{ topic }} and {{ topic.detail }}"),
            ("no_references_at_all", "static text only"),
        ],
    )
    def test_guarded_references_produce_no_findings(self, topic: str, template_source: str):
        findings = detect_unguarded_optional_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
            optional_variable_names={"assessment"},
        )
        assert findings == [], f"{topic}: expected no findings, got {findings}"

    @pytest.mark.parametrize(
        ("topic", "template_source", "expected_path"),
        [
            ("bare_interpolation", "{{ assessment }}", "assessment"),
            ("deep_access", "{{ assessment.amount }}", "assessment.amount"),
            ("guard_on_other_var", "{% if topic %}{{ assessment }}{% endif %}", "assessment"),
            ("else_branch_use", "{% if assessment %}x{% else %}{{ assessment.amount }}{% endif %}", "assessment.amount"),
            ("for_iteration", "{% for item in assessment %}{{ item }}{% endfor %}", "assessment"),
            ("deep_access_in_test", "{% if assessment.flag %}x{% endif %}", "assessment.flag"),
            ("filtered_unguarded", "{{ assessment|length }}", "assessment"),
            ("inline_cond_else_side", "{{ 'x' if topic else assessment.amount }}", "assessment.amount"),
            ("tag_filter_from_plain_at_sigil", '{{ assessment|tag("assessment") }}', "assessment"),
        ],
    )
    def test_unguarded_references_are_reported(self, topic: str, template_source: str, expected_path: str):
        findings = detect_unguarded_optional_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source=template_source,
            optional_variable_names={"assessment"},
        )
        assert len(findings) == 1, f"{topic}: expected one finding, got {findings}"
        assert findings[0].variable_name == "assessment"
        assert findings[0].path == expected_path

    def test_multiple_optional_variables_reported_independently(self):
        findings = detect_unguarded_optional_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{% if extra %}{{ extra }}{% endif %} {{ assessment }} {{ note.detail }}",
            optional_variable_names={"assessment", "note", "extra"},
        )
        assert {(finding.variable_name, finding.path) for finding in findings} == {
            ("assessment", "assessment"),
            ("note", "note.detail"),
        }

    def test_guard_does_not_leak_outside_its_block(self):
        findings = detect_unguarded_optional_references(
            template_category=TemplateCategory.LLM_PROMPT,
            template_source="{% if assessment %}{{ assessment }}{% endif %}{{ assessment }}",
            optional_variable_names={"assessment"},
        )
        assert len(findings) == 1
        assert findings[0].path == "assessment"

    def test_expression_category_supported(self):
        """The PipeCondition presence-branching idiom (design §15) lints clean."""
        findings = detect_unguarded_optional_references(
            template_category=TemplateCategory.EXPRESSION,
            template_source="{{ 'present' if penalty_clause is defined else 'absent' }}",
            optional_variable_names={"penalty_clause"},
        )
        assert findings == []
