from collections.abc import Mapping
from typing import Annotated, Any, Literal, Self, cast

from jinja2 import TemplateSyntaxError
from pydantic import Field, WithJsonSchema, field_validator, model_validator
from typing_extensions import override

from pipelex.core.concepts.choice_options import OutcomeTable, OutcomeValue, outcome_pipe, parse_outcome
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.tools.jinja2.exceptions import TEMPLATE_NESTING_ERRORS, TEMPLATE_NESTING_FAULT, Jinja2DetectVariablesError
from pipelex.tools.jinja2.jinja2_environment import make_jinja2_env_without_loader
from pipelex.tools.jinja2.jinja2_parsing import are_authored_templates_trusted
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list

#: The field a bundle writes a condition's expression in: a template as written, or an expression.
ConditionExpressionField = Literal["expression_template", "expression"]

OutcomeMap = dict[str, str]
"""Expression result -> pipe reference (or special outcome), the words of every outcome table set aside."""
AuthoredOutcomeMap = Mapping[str, OutcomeValue]
"""Expression result -> outcome, as authored: a pipe reference, or an outcome table carrying words beside it."""


OUTCOME_TABLE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pipe": {"type": "string", "minLength": 1},
        "label": {"type": "string", "minLength": 1},
        "description": {"type": "string", "minLength": 1},
        "tone": {"type": "string", "enum": ["positive", "caution", "negative", "neutral"]},
    },
    "required": ["pipe"],
    "additionalProperties": False,
}
"""An outcome table as the JSON Schema of the language states it, inline so the published schema needs no definition of it."""


class PipeConditionBlueprint(PipeBlueprint):
    type: Literal["PipeCondition"] = "PipeCondition"
    pipe_category: Literal["PipeController"] = "PipeController"
    expression_template: str | None = None
    expression: str | None = None
    outcomes: Annotated[
        AuthoredOutcomeMap,
        WithJsonSchema(
            {
                "additionalProperties": {"anyOf": [{"type": "string"}, OUTCOME_TABLE_JSON_SCHEMA]},
                "type": "object",
                "x-schema-required": True,
            }
        ),
    ] = Field(default_factory=dict)
    default_outcome: str | SpecialOutcome | OutcomeTable
    add_alias_from_expression_to: str | None = None

    @field_validator("outcomes", mode="before")
    @classmethod
    def read_outcome_tables(cls, outcomes: Any) -> Any:
        """Read each outcome table into normal form: one carrying `pipe` alone is its pipe's string (`parse_outcome`)."""
        if not isinstance(outcomes, dict):
            return outcomes
        authored = cast("dict[Any, Any]", outcomes)
        return {key: parse_outcome(raw=value) for key, value in authored.items()}

    @field_validator("default_outcome", mode="before")
    @classmethod
    def read_default_outcome_table(cls, default_outcome: Any) -> Any:
        return parse_outcome(raw=default_outcome)

    @model_validator(mode="after")
    def refuse_shared_outcome_labels(self) -> Self:
        """No two outcomes of one PipeCondition, its default included, carry the same label."""
        labels = [outcome.label for outcome in [*self.outcomes.values(), self.default_outcome] if isinstance(outcome, OutcomeTable) and outcome.label]
        seen_labels: set[str] = set()
        for label in labels:
            if label in seen_labels:
                msg = f"Two outcomes of this PipeCondition share the label '{label}': give each outcome its own label"
                raise ValueError(msg)
            seen_labels.add(label)
        return self

    @property
    def outcome_pipes(self) -> OutcomeMap:
        """Expression result -> pipe reference (or special outcome), whichever form each outcome was written in."""
        return {key: outcome_pipe(outcome=outcome) for key, outcome in self.outcomes.items()}

    @property
    def default_outcome_pipe(self) -> str:
        """The pipe reference (or special outcome) the default outcome names, whichever form wrote it."""
        return outcome_pipe(outcome=self.default_outcome)

    @property
    @override
    def pipe_dependencies(self) -> set[str]:
        """Return the set of pipe codes from outcomes and default_pipe_code.

        Excludes special pipe codes like 'continue'.
        """
        pipe_codes = set(self.outcome_pipes.values())
        if self.default_outcome_pipe:
            pipe_codes.add(self.default_outcome_pipe)
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

    @property
    def runtime_expression_field(self) -> ConditionExpressionField:
        """The field the bundle writes the condition in, which a refusal of its expression is located on.

        ``expression_template`` when it gives one, else ``expression``, the field ``runtime_expression`` reads first.
        """
        return "expression_template" if self.expression_template else "expression"

    @field_validator("outcomes", mode="after")
    @classmethod
    def validate_outcome_map(cls, outcomes: AuthoredOutcomeMap) -> AuthoredOutcomeMap:
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
        # It is then compiled as the run compiles it before rendering, in the same environment, which refuses what
        # parses but cannot be built, such as a filter or a test that does not exist: the run would refuse it on
        # every input, so the refusal is no stricter for being made at load. Jinja2 resolves a filter or a test inside
        # a conditional only when it renders, so a wrong name there compiles and is left to the run, as it must be:
        # refusing it here would refuse an expression whose run never reaches it.
        # The message quotes neither the expression nor the parser's diagnosis, which names the token it stopped at:
        # the verdict's item shows it to the caller, and the condition may be a host library's.
        # Both are judgments of what the author wrote, made where the method was validated: a build of templates already
        # judged (`trusting_authored_templates`) skips them, since they parse and compile the expression again and store
        # nothing a run reads. The built pipe reads its expression's paths itself, and the run compiles it.
        if are_authored_templates_trusted():
            return
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["expression_template", "expression"]):
            # Both fields or neither: the validator of the pair refuses that and says why, where a refusal of the
            # parse of one of them, which runs first, would hide it.
            return
        runtime_expression = self.runtime_expression
        if runtime_expression is None:
            return
        field_name = self.runtime_expression_field
        wanted = "a Jinja2 template" if self.expression_template else "a Jinja2 expression"
        try:
            detect_jinja2_required_variables(template_category=TemplateCategory.EXPRESSION, template_source=runtime_expression)
        except Jinja2DetectVariablesError as exc:
            msg = f"The '{field_name}' of this PipeCondition {describe_expression_parse_failure(error=exc)}. Fix it so that it parses as {wanted}."
            raise ValueError(msg) from exc.__cause__
        try:
            make_jinja2_env_without_loader(template_category=TemplateCategory.EXPRESSION).compile(runtime_expression)
        except TEMPLATE_NESTING_ERRORS as exc:
            msg = f"The '{field_name}' of this PipeCondition does not compile: {TEMPLATE_NESTING_FAULT}"
            raise ValueError(msg) from exc
        except TemplateSyntaxError as exc:
            msg = (
                f"The '{field_name}' of this PipeCondition does not compile at line {exc.lineno} of that expression. "
                f"Check that every filter and test it names exists, and fix it so that it compiles as {wanted}."
            )
            raise ValueError(msg) from exc

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
