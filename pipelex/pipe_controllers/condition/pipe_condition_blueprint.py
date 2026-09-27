from typing import Annotated, Literal, Self

from jinja2 import TemplateSyntaxError
from pydantic import Field, WithJsonSchema, field_validator, model_validator
from typing_extensions import override

from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.exceptions import Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list

OutcomeMap = dict[str, str]


class PipeConditionBlueprint(PipeBlueprint):
    type: Literal["PipeCondition"] = "PipeCondition"
    pipe_category: Literal["PipeController"] = "PipeController"
    expression_template: str | None = None
    expression: str | None = None
    outcomes: Annotated[
        OutcomeMap,
        WithJsonSchema(
            {
                "additionalProperties": {"type": "string"},
                "type": "object",
                "x-schema-required": True,
            }
        ),
    ] = Field(default_factory=OutcomeMap)
    default_outcome: str | SpecialOutcome
    add_alias_from_expression_to: str | None = None

    @property
    @override
    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes from outcomes and default_pipe_code.

        Excludes special pipe codes like 'continue'.
        """
        pipe_codes = set(self.outcomes.values())
        if self.default_outcome:
            pipe_codes.add(self.default_outcome)
        return pipe_codes - set(SpecialOutcome.value_list())

    @property
    def runtime_expression(self) -> str | None:
        """The Jinja2 template the built ``PipeCondition`` renders to choose its outcome, or ``None`` when neither field gives one.

        An ``expression_template`` is the template as written; an ``expression`` is wrapped in ``{{ … }}``. Neither
        adds a line, so a line of the template is the same line of the field the author wrote.
        """
        if self.expression_template:
            return self.expression_template
        if self.expression:
            return "{{ " + self.expression + " }}"
        return None

    @field_validator("outcomes", mode="after")
    @classmethod
    def validate_outcome_map(cls, outcomes: OutcomeMap) -> OutcomeMap:
        if not outcomes:
            msg = f"PipeConditionBlueprint must have at least one mapping in outcomes, got: {outcomes}"
            raise ValueError(msg)
        return outcomes

    @model_validator(mode="after")
    def validate_expression_and_expression_template(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["expression_template", "expression"]):
            msg = "PipeCondition should have exactly one of 'expression_template' or 'expression'"
            raise ValueError(msg)
        return self

    @override
    def validate_inputs(self):
        # The expression is parsed where the bundle loads, so every surface that loads it refuses an expression that
        # does not parse as an item of its verdict, located on the pipe, as it refuses a prompt or a template that
        # does not parse. The parse is the one the built pipe makes when it reads the variables its expression needs.
        # The message quotes neither the expression nor the parser's diagnosis, which names the token it stopped at:
        # the verdict is kept verbatim under STRICT disclosure, and the condition may be a host library's.
        runtime_expression = self.runtime_expression
        if runtime_expression is None:
            return
        try:
            detect_jinja2_required_variables(template_category=TemplateCategory.EXPRESSION, template_source=runtime_expression)
        except Jinja2DetectVariablesError as exc:
            field_name = "expression_template" if self.expression_template else "expression"
            wanted = "a Jinja2 template" if self.expression_template else "a Jinja2 expression"
            msg = f"The '{field_name}' of this PipeCondition {describe_expression_parse_failure(error=exc)}. Fix it so that it parses as {wanted}."
            raise ValueError(msg) from exc.__cause__

    @override
    def validate_output(self):
        pass


def describe_expression_parse_failure(*, error: Jinja2DetectVariablesError) -> str:
    """Say where a condition's expression fails to parse, in words that owe nothing to the expression.

    Every layer between Jinja2 and the condition puts the expression in its message, and Jinja2's own
    diagnosis quotes the token it stopped at, so no text of the error can be passed on. The parser's line,
    counted within the expression, is what locates the fault.
    """
    cause: BaseException | None = error.__cause__
    while cause is not None:
        if isinstance(cause, TemplateSyntaxError):
            return f"does not parse at line {cause.lineno} of that expression"
        cause = cause.__cause__
    return "does not parse"
