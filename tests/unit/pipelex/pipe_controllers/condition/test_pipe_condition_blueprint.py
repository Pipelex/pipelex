import pytest
from pydantic import ValidationError

from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome


class TestPipeConditionBlueprint:
    def test_pipe_dependencies_correct(self):
        blueprint = PipeConditionBlueprint(
            description="lorem ipsum",
            inputs={"status": "Text"},
            output="Text",
            expression="status",
            outcomes={"active": "process_active", "inactive": "process_inactive"},
            default_outcome="process_default",
        )
        assert blueprint.pipe_dependencies == {"process_active", "process_inactive", "process_default"}

        blueprint = PipeConditionBlueprint(
            description="lorem ipsum",
            inputs={"type": "Text"},
            output="Text",
            expression="type",
            outcomes={"A": "handle_a"},
            default_outcome=SpecialOutcome.FAIL,
        )
        assert blueprint.pipe_dependencies == {"handle_a"}

        blueprint = PipeConditionBlueprint(
            description="lorem ipsum",
            inputs={"flag": "Text"},
            output="Text",
            expression="flag",
            outcomes={"yes": "process_yes", "no": "process_no"},
            default_outcome=SpecialOutcome.CONTINUE,
        )
        assert blueprint.pipe_dependencies == {"process_yes", "process_no"}

    def test_validate_outcome_map_correct(self):
        blueprint = PipeConditionBlueprint(
            description="lorem ipsum",
            inputs={"value": "Text"},
            output="Text",
            expression="value",
            outcomes={"high": "process_high"},
            default_outcome="process_default",
        )
        assert blueprint.outcomes == {"high": "process_high"}

        blueprint = PipeConditionBlueprint(
            description="lorem ipsum",
            inputs={"status": "Text"},
            output="Text",
            expression="status",
            outcomes={"active": "process_active", "inactive": "process_inactive"},
            default_outcome="process_default",
        )
        assert len(blueprint.outcomes) == 2

    def test_validate_outcome_map_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            PipeConditionBlueprint(
                description="lorem ipsum",
                inputs={"value": "Text"},
                output="Text",
                expression="value",
                outcomes={},
                default_outcome="process_default",
            )
        assert "PipeConditionBlueprint must have at least one mapping in outcomes" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("expression", "expression_template", "field_name", "line", "wanted", "expression_text"),
        [
            ("lane ==", None, "expression", 1, "a Jinja2 expression", "lane =="),
            ("{% if %}", None, "expression", 1, "a Jinja2 expression", "{% if %}"),
            (
                None,
                "{% if lane == 'express' %}express\n{% frobnicate_the_parcel %}{% endif %}",
                "expression_template",
                2,
                "a Jinja2 template",
                "frobnicate_the_parcel",
            ),
        ],
        ids=["dangling_operator", "tag_inside_expression", "unknown_tag_on_line_2"],
    )
    def test_an_expression_that_does_not_parse_is_refused_by_its_line_only(
        self, expression: str | None, expression_template: str | None, field_name: str, line: int, wanted: str, expression_text: str
    ):
        """The refusal names the field and the line it fails at, never a token of the expression or of the parser's diagnosis."""
        with pytest.raises(ValidationError) as exc_info:
            PipeConditionBlueprint(
                description="Choose the lane a parcel goes down",
                inputs={"lane": "Text"},
                output="Text",
                expression=expression,
                expression_template=expression_template,
                outcomes={"express": "send_express"},
                default_outcome="send_standard",
            )

        (error,) = exc_info.value.errors()
        assert error["msg"] == (
            f"Value error, The '{field_name}' of this PipeCondition does not parse at line {line} of that expression. "
            f"Fix it so that it parses as {wanted}."
        )
        assert expression_text not in error["msg"]

    @pytest.mark.parametrize(
        ("expression", "expression_template", "field_name", "line", "wanted", "expression_text"),
        [
            ("lane | lenght_of_lane", None, "expression", 1, "a Jinja2 expression", "lenght_of_lane"),
            ("lane is frobbed_lane", None, "expression", 1, "a Jinja2 expression", "frobbed_lane"),
            (None, "{{ lane }}\n{{ lane | frobnicate_the_parcel }}", "expression_template", 2, "a Jinja2 template", "frobnicate_the_parcel"),
        ],
        ids=["unknown_filter", "unknown_test", "unknown_filter_on_line_2"],
    )
    def test_an_expression_that_parses_but_does_not_compile_is_refused_by_its_line_only(
        self, expression: str | None, expression_template: str | None, field_name: str, line: int, wanted: str, expression_text: str
    ):
        """An expression the run could not compile, such as one naming a filter that does not exist, is refused at load by its line."""
        with pytest.raises(ValidationError) as exc_info:
            PipeConditionBlueprint(
                description="Choose the lane a parcel goes down",
                inputs={"lane": "Text"},
                output="Text",
                expression=expression,
                expression_template=expression_template,
                outcomes={"express": "send_express"},
                default_outcome="send_standard",
            )

        (error,) = exc_info.value.errors()
        assert error["msg"] == (
            f"Value error, The '{field_name}' of this PipeCondition does not compile at line {line} of that expression. "
            f"Check that every filter and test it names exists, and fix it so that it compiles as {wanted}."
        )
        assert expression_text not in error["msg"]

    def test_an_expression_using_a_filter_jinja2_has_is_accepted(self):
        blueprint = PipeConditionBlueprint(
            description="Choose the lane a parcel goes down",
            inputs={"lane": "Text"},
            output="Text",
            expression="lane | lower",
            outcomes={"express": "send_express"},
            default_outcome="send_standard",
        )
        assert blueprint.runtime_expression == "{{ lane | lower }}"

    def test_both_fields_are_refused_as_such_even_when_the_template_does_not_parse(self):
        """Declaring both fields is the fault reported, not the parse of the template the author may not have meant to keep."""
        with pytest.raises(ValidationError) as exc_info:
            PipeConditionBlueprint(
                description="Choose the lane a parcel goes down",
                inputs={"lane": "Text"},
                output="Text",
                expression="lane",
                expression_template="{% if %}",
                outcomes={"express": "send_express"},
                default_outcome="send_standard",
            )

        (error,) = exc_info.value.errors()
        assert error["msg"] == "Value error, PipeCondition should have exactly one of 'expression_template' or 'expression'"

    def test_the_runtime_expression_is_the_template_or_the_wrapped_expression(self):
        from_expression = PipeConditionBlueprint(
            description="Choose the lane a parcel goes down",
            inputs={"lane": "Text"},
            output="Text",
            expression="lane",
            outcomes={"express": "send_express"},
            default_outcome="send_standard",
        )
        from_template = PipeConditionBlueprint(
            description="Choose the lane a parcel goes down",
            inputs={"lane": "Text"},
            output="Text",
            expression_template="{% if lane %}{{ lane }}{% endif %}",
            outcomes={"express": "send_express"},
            default_outcome="send_standard",
        )

        assert from_expression.runtime_expression == "{{ lane }}"
        assert from_template.runtime_expression == "{% if lane %}{{ lane }}{% endif %}"
