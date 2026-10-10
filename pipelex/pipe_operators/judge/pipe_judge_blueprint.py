from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import override

from pipelex.cogt.judgment.judgment_models import JudgmentKind, RatingLevel
from pipelex.cogt.judgment.judgment_setting import JudgmentModelChoice
from pipelex.cogt.templating.exceptions import TemplateSigilSyntaxError
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.pipe_machinery.pipe_blueprint import PipeBlueprint
from pipelex.pipe_machinery.validation import check_inputs_match_variables
from pipelex.tools.jinja2.exceptions import Jinja2TemplateSyntaxError
from pipelex.tools.jinja2.jinja2_parsing import check_jinja2_parsing
from pipelex.tools.jinja2.jinja2_required_variables import detect_jinja2_required_variables
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path


class JudgeYesNoCriteria(BaseModel):
    """What a yes and a no mean, for a yes/no question: both sides, each non-empty. Closed: a key other than `yes` or `no` is refused.

    The judging vendors silently ignore a criterion key they do not know, so this model is the only
    place a typo in one is caught. Both sides are required because a lone side cannot be carried with
    its meaning on every backend: one sends a single criterion as one of a pair of options, where the
    side left out would be a blank.
    """

    model_config = ConfigDict(extra="forbid")

    yes: str
    no: str

    @model_validator(mode="before")
    @classmethod
    def refuse_a_lone_side(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        raw_criteria = cast("dict[str, Any]", values)
        if not raw_criteria:
            msg = "Criteria describe both answers, and this table declares neither: write both `yes` and `no`, or remove the table."
            raise ValueError(msg)
        declared_sides = [side for side in ("yes", "no") if side in raw_criteria]
        if len(declared_sides) == 1:
            declared_side = declared_sides[0]
            missing_side = "no" if declared_side == "yes" else "yes"
            msg = (
                f"Criteria describe both answers, and these declare `{declared_side}` without `{missing_side}`: "
                f"write `{missing_side}` as the complement of `{declared_side}`."
            )
            raise ValueError(msg)
        return raw_criteria

    @model_validator(mode="after")
    def validate_sides_are_not_empty(self) -> Self:
        for side, description in (("yes", self.yes), ("no", self.no)):
            if not description.strip():
                msg = f"Criteria describe both answers, so `{side}` cannot be empty."
                raise ValueError(msg)
        return self


class JudgeRatingLevel(BaseModel):
    """A rating level written as a table: a `label` naming it in a few words, a `description` of the situation it stands for, or both.

    Closed, as the standard requires. A level written as a plain string is its description.
    """

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    description: str | None = None


class PipeJudgeBlueprint(PipeBlueprint):
    """Asks a judging model one closed question about the evidence its prompt presents: yes/no, a choice, or a rating.

    `prompt` is the evidence template, rendered and checked as a PipeLLM's prompt is, the images and
    documents it reads presented to the model as files. `question` is the instruction, a plain text
    template. The kind is decided by which of `options` and `levels` the pipe declares, never by a
    field of its own. Every declared input is read by the prompt or by the question.
    """

    type: Literal["PipeJudge"] = "PipeJudge"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    prompt: str
    question: str
    model: JudgmentModelChoice | None = None
    options: dict[str, str] | None = None
    levels: list[str | JudgeRatingLevel] | None = None
    criteria: JudgeYesNoCriteria | None = None
    threshold: float | None = None

    @model_validator(mode="before")
    @classmethod
    def refuse_a_missing_prompt_or_question(cls, values: Any) -> Any:
        """Name the field a bundle written for the old operator gets wrong, where pydantic would only say one is missing.

        Before this version `prompt` was a synonym of `question`, so a table setting `prompt` alone most
        likely holds a question. An empty prompt or question is refused here too.
        """
        if not isinstance(values, dict):
            return values
        raw_table = cast("dict[str, Any]", values)
        if "question" not in raw_table:
            msg = (
                "A PipeJudge asks a question about the evidence of its prompt, and this one sets no `question`: "
                "`prompt` holds the evidence the question is asked over, and the question is written in `question`."
            )
            raise ValueError(msg)
        if "prompt" not in raw_table:
            msg = (
                "A PipeJudge judges the evidence its `prompt` presents, and this one sets no `prompt`: write the evidence "
                'as a template that reads the inputs, such as `prompt = "@message"`.'
            )
            raise ValueError(msg)
        # Refused here rather than after validation, so an empty template is named before the input check
        # reports the inputs it leaves unread.
        prompt = raw_table["prompt"]
        if isinstance(prompt, str) and not prompt.strip():
            msg = "A PipeJudge judges the evidence its prompt presents, so its `prompt` cannot be empty."
            raise ValueError(msg)
        question = raw_table["question"]
        if isinstance(question, str) and not question.strip():
            msg = "A PipeJudge asks one question, so its `question` cannot be empty."
            raise ValueError(msg)
        return raw_table

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
            _validate_levels(levels=self.levels)
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

    @property
    def rating_levels(self) -> list[RatingLevel] | None:
        """The scale as the judgment family carries it: a string level is its description."""
        if self.levels is None:
            return None
        rating_levels: list[RatingLevel] = []
        for level in self.levels:
            if isinstance(level, str):
                rating_levels.append(RatingLevel(description=level))
            else:
                rating_levels.append(RatingLevel(label=level.label, description=level.description))
        return rating_levels

    @override
    def validate_inputs(self):
        """The two-way check every operator that reads its inputs through templates applies, over the prompt and the question together."""
        declared_inputs: set[str] = set(self.inputs.keys()) if self.inputs else set()
        variable_paths = _template_variable_paths(
            template_source=self.prompt, template_category=TemplateCategory.LLM_PROMPT, declared_inputs=declared_inputs, field_name="prompt"
        )
        variable_paths |= _template_variable_paths(
            template_source=self.question, template_category=TemplateCategory.BASIC, declared_inputs=declared_inputs, field_name="question"
        )
        check_inputs_match_variables(declared_inputs=declared_inputs, variable_paths=variable_paths, reader="prompt or question")

    @override
    def validate_output(self):
        parsed_output = parse_concept_with_multiplicity(concept_ref_or_code=self.output)
        if parsed_output.multiplicity:
            msg = (
                f"A PipeJudge produces one verdict, so its output carries no multiplicity, and this one declares '{self.output}'. "
                "To judge each item of a list, map the PipeJudge over it with a PipeBatch."
            )
            raise ValueError(msg)


def _validate_levels(*, levels: list[str | JudgeRatingLevel]) -> None:
    """A scale of at least two levels, none empty, its labels all or none and distinct, since a label is what the verdict reports."""
    if len(levels) < 2:
        msg = f"A rating question needs at least two `levels` on its scale, and this one declares {len(levels)}."
        raise ValueError(msg)
    labels: list[str] = []
    for index_level, level in enumerate(levels):
        if isinstance(level, str):
            if not level.strip():
                msg = f"Every level of a rating question describes a situation, so none may be empty: level {index_level} is."
                raise ValueError(msg)
            continue
        if level.label is None and level.description is None:
            msg = f"A rating level written as a table carries a `label`, a `description` or both, and level {index_level} carries neither."
            raise ValueError(msg)
        for field_name, field_value in (("label", level.label), ("description", level.description)):
            if field_value is not None and not field_value.strip():
                msg = f"A rating level's `{field_name}` cannot be empty, and level {index_level}'s is."
                raise ValueError(msg)
        if level.label is not None:
            labels.append(level.label)
    if labels and len(labels) != len(levels):
        msg = "On a rating scale every level carries a `label` or none does, and this one labels some of its levels only."
        raise ValueError(msg)
    duplicated_labels = sorted({label for label in labels if labels.count(label) > 1})
    if duplicated_labels:
        repeated = ", ".join(f"'{label}'" for label in duplicated_labels)
        msg = f"A rating verdict reports the label of its level, so the labels of one scale are distinct, and {repeated} is repeated."
        raise ValueError(msg)


def _template_variable_paths(*, template_source: str, template_category: TemplateCategory, declared_inputs: set[str], field_name: str) -> set[str]:
    """The full dotted paths a template reads, rid of the internal names that start with an underscore."""
    try:
        preprocessed_template = preprocess_template(template_source, declared_inputs=declared_inputs)
    except TemplateSigilSyntaxError as exc:
        msg = f"Template sigil error in PipeJudge {field_name}: {exc}"
        raise ValueError(msg) from exc
    try:
        check_jinja2_parsing(template_source=preprocessed_template, template_category=template_category)
    except Jinja2TemplateSyntaxError as exc:
        msg = f"Could not parse the {field_name} template for PipeJudge: {exc}"
        raise ValueError(msg) from exc
    full_paths = detect_jinja2_required_variables(template_category=template_category, template_source=preprocessed_template)
    return {path for path in full_paths if not get_root_from_dotted_path(path).startswith("_")}
