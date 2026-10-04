from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import override

from pipelex.cogt.judgment.judgment_models import JudgmentKind
from pipelex.cogt.judgment.judgment_setting import JudgmentModelChoice
from pipelex.cogt.templating.exceptions import TemplateSigilSyntaxError
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.pipe_machinery.validation import check_variables_are_declared
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

# The one synonym the language admits: every other inference operator calls its template `prompt`.
QUESTION_SYNONYM = "prompt"


class JudgeYesNoCriteria(BaseModel):
    """What a yes and a no mean, for a yes/no question. Closed: a key other than `yes` or `no` is refused.

    The judging vendor silently ignores a criterion key it does not know, so this model is the only
    place a typo in one is caught.
    """

    model_config = ConfigDict(extra="forbid")

    yes: str | None = None
    no: str | None = None


class PipeJudgeBlueprint(PipeBlueprint):
    """Asks a judging model one closed question about its inputs: yes/no, a choice, or a rating.

    The kind is decided by which of `options` and `levels` the pipe declares, never by a field of its
    own. `prompt` is accepted in place of `question` and read exactly as it, so nothing after parsing
    sees the synonym. Every declared input is material to judge, so an input the question never names
    is still read; only a variable the question names must be declared.
    """

    type: Literal["PipeJudge"] = "PipeJudge"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    question: str
    model: JudgmentModelChoice | None = None
    options: dict[str, str] | None = None
    levels: list[str] | None = None
    criteria: JudgeYesNoCriteria | None = None
    threshold: float | None = None

    @model_validator(mode="before")
    @classmethod
    def read_prompt_as_question(cls, values: dict[str, Any]) -> dict[str, Any]:
        if QUESTION_SYNONYM not in values:
            return values
        if "question" in values:
            msg = f"A PipeJudge sets `question`, or `{QUESTION_SYNONYM}` as its synonym, but not both: remove one of the two."
            raise ValueError(msg)
        fields = dict(values)
        fields["question"] = fields.pop(QUESTION_SYNONYM)
        return fields

    @model_validator(mode="after")
    def validate_question_kind(self) -> Self:
        if self.options is not None and self.levels is not None:
            msg = "A PipeJudge declares `options` for a choice question or `levels` for a rating question, not both."
            raise ValueError(msg)
        if self.options is not None or self.levels is not None:
            kind_field = "options" if self.options is not None else "levels"
            for yes_no_field in ("criteria", "threshold"):
                if getattr(self, yes_no_field) is not None:
                    msg = (
                        f"`{yes_no_field}` applies to a yes/no question only, and this PipeJudge declares `{kind_field}`, "
                        f"which makes it a {self.judgment_kind} question. Remove `{yes_no_field}`."
                    )
                    raise ValueError(msg)
        if self.options is not None:
            if len(self.options) < 2:
                msg = f"A choice question needs at least two `options` to choose between, and this one declares {len(self.options)}."
                raise ValueError(msg)
            if any(not option.strip() for option in self.options):
                msg = "Every key of `options` names an option, so none may be empty."
                raise ValueError(msg)
        if self.levels is not None:
            if len(self.levels) < 2:
                msg = f"A rating question needs at least two `levels` on its scale, and this one declares {len(self.levels)}."
                raise ValueError(msg)
            empty_indices = [index for index, level in enumerate(self.levels) if not level.strip()]
            if empty_indices:
                msg = f"Every level of a rating question describes a situation, so none may be empty: level {empty_indices[0]} is."
                raise ValueError(msg)
        if self.threshold is not None and not 0 < self.threshold < 1:
            msg = f"`threshold` is a probability of yes strictly between 0 and 1, and this PipeJudge declares {self.threshold}."
            raise ValueError(msg)
        return self

    @property
    def judgment_kind(self) -> JudgmentKind:
        if self.options is not None:
            return JudgmentKind.CHOICE
        if self.levels is not None:
            return JudgmentKind.RATING
        return JudgmentKind.YES_NO

    @override
    def validate_inputs(self):
        template_category = TemplateCategory.BASIC
        declared_inputs: set[str] = set(self.inputs.keys()) if self.inputs else set()
        try:
            preprocessed_template = preprocess_template(self.question, declared_inputs=declared_inputs)
        except TemplateSigilSyntaxError as exc:
            msg = f"Template sigil error in PipeJudge question: {exc}"
            raise ValueError(msg) from exc
        try:
            check_jinja2_parsing(
                template_source=preprocessed_template,
                template_category=template_category,
            )
        except Jinja2TemplateSyntaxError as exc:
            msg = f"Could not parse the question template for PipeJudge: {exc}"
            raise ValueError(msg) from exc

        full_paths = detect_jinja2_required_variables(
            template_category=template_category,
            template_source=preprocessed_template,
        )
        # Names starting with an underscore are internal and never count as read inputs
        variable_paths = {path for path in full_paths if not get_root_from_dotted_path(path).startswith("_")}
        # Every declared input is material to judge, read whether the question names it or not: only
        # the variables the question does name must be declared.
        check_variables_are_declared(
            declared_inputs=declared_inputs, variable_paths=variable_paths, reader="question", dotted_input_supplies_its_path=False
        )

    @override
    def validate_output(self):
        parsed_output = parse_concept_with_multiplicity(concept_ref_or_code=self.output)
        if parsed_output.multiplicity:
            msg = (
                f"A PipeJudge produces one verdict, so its output carries no multiplicity, and this one declares '{self.output}'. "
                "To judge each item of a list, map the PipeJudge over it with a PipeBatch."
            )
            raise ValueError(msg)
