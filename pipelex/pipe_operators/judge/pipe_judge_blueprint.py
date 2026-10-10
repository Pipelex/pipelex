from typing import Any, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import override

from pipelex.cogt.judgment.judgment_models import JudgmentKind, RatingLevel
from pipelex.cogt.judgment.judgment_setting import JudgmentModelChoice
from pipelex.cogt.templating.exceptions import TemplateSigilSyntaxError
from pipelex.cogt.templating.template_preprocessor import preprocess_template
from pipelex.core.concepts.concept_structure_blueprint import is_admitted_structure_field_name
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


# The fields that decide a question's kind and its verdict, which the single form sets on the pipe and the
# multi form on each of its questions.
QUESTION_KIND_FIELDS = ("options", "levels", "criteria", "threshold")


class JudgeQuestionBlueprint(BaseModel):
    """One question of a PipeJudge asking several: what it asks, and the fields the single form sets on the pipe.

    Closed, as the standard requires: `question` is the instruction, a plain text template, and the kind
    is decided by which of `options` and `levels` the question declares, under the single form's rules.
    Its key in `questions` names the output field holding its verdict.
    """

    model_config = ConfigDict(extra="forbid")

    question: str
    options: dict[str, str] | None = None
    levels: list[str | JudgeRatingLevel] | None = None
    criteria: JudgeYesNoCriteria | None = None
    threshold: float | None = None

    @model_validator(mode="before")
    @classmethod
    def refuse_a_missing_or_empty_question(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        raw_table = cast("dict[str, Any]", values)
        if raw_table.get("question") is None:
            msg = "Each question of `questions` writes what it asks in `question`, and this one sets none."
            raise ValueError(msg)
        question = raw_table["question"]
        if isinstance(question, str) and not question.strip():
            msg = "Each question of `questions` asks something, so its `question` cannot be empty."
            raise ValueError(msg)
        return raw_table

    @model_validator(mode="after")
    def validate_question_kind(self) -> Self:
        _validate_question_kind(options=self.options, levels=self.levels, criteria=self.criteria, threshold=self.threshold, noun="question")
        return self

    @property
    def judgment_kind(self) -> JudgmentKind:
        return _judgment_kind_of(options=self.options, levels=self.levels)

    @property
    def rating_levels(self) -> list[RatingLevel] | None:
        """The scale as the judgment family carries it: a string level is its description."""
        return _rating_levels_of(levels=self.levels)


class PipeJudgeBlueprint(PipeBlueprint):
    """Asks a judging model closed questions about the evidence its prompt presents: yes/no, a choice, or a rating.

    `prompt` is the evidence template, rendered and checked as a PipeLLM's prompt is, the images and
    documents it reads presented to the model as files. The single form asks one `question`, a plain
    text template, and produces its verdict native; the multi form asks the several `questions` of a
    table keyed by name over the same evidence in one request, and fills a structure whose fields are
    those names with one verdict each. A question's kind is decided by which of `options` and `levels`
    it declares, never by a field of its own, and the single form declares them on the pipe. Every
    declared input is read by the prompt or by a question.
    """

    type: Literal["PipeJudge"] = "PipeJudge"
    pipe_category: Literal["PipeOperator"] = "PipeOperator"
    prompt: str
    question: str | None = None
    questions: dict[str, JudgeQuestionBlueprint] | None = None
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
        likely holds a question. A pipe asks one `question` or several `questions`, never both. A field
        written as null holds no value, as a dump writes the form not taken, so the form is read off the
        values rather than the keys. An empty prompt or question is refused here too.
        """
        if not isinstance(values, dict):
            return values
        raw_table = cast("dict[str, Any]", values)
        sets_question = raw_table.get("question") is not None
        sets_questions = raw_table.get("questions") is not None
        if not sets_question and not sets_questions:
            msg = (
                "A PipeJudge asks a question about the evidence of its prompt, and this one sets no `question`: "
                "`prompt` holds the evidence the question is asked over, and the question is written in `question`, "
                "or several in `questions`."
            )
            raise ValueError(msg)
        if sets_question and sets_questions:
            msg = (
                "A PipeJudge asks one `question` or several `questions`, and this one sets both `question` and `questions`: "
                "keep `question` for a single verdict, or move it into `questions`."
            )
            raise ValueError(msg)
        if raw_table.get("prompt") is None:
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
        question = raw_table.get("question")
        if isinstance(question, str) and not question.strip():
            msg = "A PipeJudge asks one question, so its `question` cannot be empty."
            raise ValueError(msg)
        return raw_table

    @model_validator(mode="after")
    def validate_question_kind(self) -> Self:
        if self.questions is None:
            _validate_question_kind(options=self.options, levels=self.levels, criteria=self.criteria, threshold=self.threshold, noun="PipeJudge")
            return self
        if not self.questions:
            msg = "A PipeJudge's `questions` holds at least one question, and this one holds none: add a question, or ask one in `question`."
            raise ValueError(msg)
        for question_name in self.questions:
            if not is_admitted_structure_field_name(field_name=question_name):
                msg = (
                    "Each key of `questions` names the output field holding its question's verdict, so it must be a name a concept "
                    f"structure admits for a field, and '{question_name}' is not: a field name is a Python identifier that is not a "
                    "Python keyword, does not start with an underscore and is not a reserved name."
                )
                raise ValueError(msg)
        for kind_field in QUESTION_KIND_FIELDS:
            if getattr(self, kind_field) is not None:
                msg = (
                    f"A PipeJudge asking several `questions` sets `{kind_field}` on each question rather than on the pipe: "
                    f"move `{kind_field}` into the question it belongs to."
                )
                raise ValueError(msg)
        return self

    @property
    def judgment_kind(self) -> JudgmentKind | None:
        """The single form's kind, read off the pipe's `options` and `levels`; `None` in the multi form, whose questions each have their own."""
        if self.questions is not None:
            return None
        return _judgment_kind_of(options=self.options, levels=self.levels)

    @property
    def rating_levels(self) -> list[RatingLevel] | None:
        """The single form's scale as the judgment family carries it: a string level is its description."""
        return _rating_levels_of(levels=self.levels)

    @override
    def validate_inputs(self):
        """The two-way check every operator that reads its inputs through templates applies, over the prompt and every question together."""
        declared_inputs: set[str] = set(self.inputs.keys()) if self.inputs else set()
        variable_paths = _template_variable_paths(
            template_source=self.prompt, template_category=TemplateCategory.LLM_PROMPT, declared_inputs=declared_inputs, field_name="prompt"
        )
        if self.questions is None:
            # The before-validator guarantees the single form's question.
            question = self.question or ""
            variable_paths |= _template_variable_paths(
                template_source=question, template_category=TemplateCategory.BASIC, declared_inputs=declared_inputs, field_name="question"
            )
            check_inputs_match_variables(declared_inputs=declared_inputs, variable_paths=variable_paths, reader="prompt or question")
            return
        for question_name, question_blueprint in self.questions.items():
            variable_paths |= _template_variable_paths(
                template_source=question_blueprint.question,
                template_category=TemplateCategory.BASIC,
                declared_inputs=declared_inputs,
                field_name=f"question '{question_name}'",
            )
        check_inputs_match_variables(declared_inputs=declared_inputs, variable_paths=variable_paths, reader="prompt or questions")

    @override
    def validate_output(self):
        parsed_output = parse_concept_with_multiplicity(concept_ref_or_code=self.output)
        if not parsed_output.multiplicity:
            return
        if self.questions is not None:
            msg = (
                f"A PipeJudge asking several questions fills one structure with their verdicts, so its output carries no multiplicity, "
                f"and this one declares '{self.output}'. To judge each item of a list, map the PipeJudge over it with a PipeBatch."
            )
            raise ValueError(msg)
        msg = (
            f"A PipeJudge produces one verdict, so its output carries no multiplicity, and this one declares '{self.output}'. "
            "To judge each item of a list, map the PipeJudge over it with a PipeBatch."
        )
        raise ValueError(msg)


def _judgment_kind_of(*, options: dict[str, str] | None, levels: list[str | JudgeRatingLevel] | None) -> JudgmentKind:
    """A question's kind, read off which of `options` and `levels` it declares."""
    if options is not None:
        return JudgmentKind.CHOICE
    if levels is not None:
        return JudgmentKind.RATING
    return JudgmentKind.YES_NO


def _rating_levels_of(*, levels: list[str | JudgeRatingLevel] | None) -> list[RatingLevel] | None:
    """A declared scale as the judgment family carries it: a string level is its description."""
    if levels is None:
        return None
    rating_levels: list[RatingLevel] = []
    for level in levels:
        if isinstance(level, str):
            rating_levels.append(RatingLevel(description=level))
        else:
            rating_levels.append(RatingLevel(label=level.label, description=level.description))
    return rating_levels


def _validate_question_kind(
    *,
    options: dict[str, str] | None,
    levels: list[str | JudgeRatingLevel] | None,
    criteria: JudgeYesNoCriteria | None,
    threshold: float | None,
    noun: str,
) -> None:
    """The single form's rules on the fields deciding a question's kind, for a pipe or for one of its questions, as `noun` names it."""
    if options is not None and levels is not None:
        msg = f"A {noun} declares `options` for a choice question or `levels` for a rating question, not both."
        raise ValueError(msg)
    if options is not None or levels is not None:
        kind_field = "options" if options is not None else "levels"
        judgment_kind = _judgment_kind_of(options=options, levels=levels)
        for yes_no_field, yes_no_value in (("criteria", criteria), ("threshold", threshold)):
            if yes_no_value is not None:
                msg = (
                    f"`{yes_no_field}` applies to a yes/no question only, and this {noun} declares `{kind_field}`, "
                    f"which makes it a {judgment_kind} question. Remove `{yes_no_field}`."
                )
                raise ValueError(msg)
    if options is not None:
        if len(options) < 2:
            msg = f"A choice question needs at least two `options` to choose between, and this one declares {len(options)}."
            raise ValueError(msg)
        if any(not option.strip() for option in options):
            msg = "Every key of `options` names an option, so none may be empty."
            raise ValueError(msg)
    if levels is not None:
        _validate_levels(levels=levels)
    if threshold is not None and not 0 < threshold < 1:
        msg = f"`threshold` is a probability of yes strictly between 0 and 1, and this {noun} declares {threshold}."
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
