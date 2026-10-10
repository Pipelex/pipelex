"""Judgment operator semantics: deck resolution, the evidence prompt, question rendering, the verdict, memory write-back.

These are the functions the interpreter's `PipeJudge` calls, and the ones a programmatic caller
invokes on a `RuntimeBoot`-only process. They read the runtime hub for the services a runtime boot
stands up (the model deck, the content generator) and take everything else as an explicit argument.

A judgment is asked over **evidence**: a prompt template, rendered against memory and assembled with
the images and documents it references exactly as a PipeLLM's user prompt is, through the shared
user-prompt assembly (`pipelex.kernel.prompt_assembly`). What the evidence holds is the template's
business, so an input reaches the judging model only when the prompt reads it. An optional input the run
was not given renders as the template's guard says, and the assembly skips its files, numbering and
handing over none of them.

A step asks one question, `run_judgment`, whose verdict native is the result, or several,
`run_multi_judgment`, whose verdicts fill a structure field by field. Either way it is one request to the
judging model, every question answered independently over the same evidence.
"""

from typing import NamedTuple

from pydantic import BaseModel, ConfigDict
from pydantic.fields import FieldInfo

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.exceptions import JudgmentAnswerMismatchError, JudgmentModelMissingError, JudgmentRefusedError, ModelNotFoundError
from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    JudgmentAnswer,
    JudgmentOutcome,
    JudgmentPrompt,
    JudgmentQuestion,
    JudgmentRefusal,
    RatingAnswer,
    RatingQuestion,
    YesNoAnswer,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentModelChoice, JudgmentSetting
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_reference import write_model_handle
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.kernel.exceptions import JudgmentOutputFieldsError
from pipelex.kernel.judgment_results import JudgmentResult, MultiJudgmentResult, QuestionJudgment
from pipelex.kernel.memory_ops import store_result
from pipelex.kernel.prompt_assembly import UserPromptContent, assemble_user_prompt
from pipelex.runtime_hub import get_content_generator, get_model_deck
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TemplatingStyle

# The one question a step asks travels under this key: the batch-first contract needs a key, and
# nothing reads it but the answer lookup below.
JUDGMENT_QUESTION_KEY = "question"

# A yes/no verdict reads its reported probability against this when the step declares no threshold.
DEFAULT_YES_NO_THRESHOLD = 0.5


class AskedQuestion(BaseModel):
    """One question of a judgment asking several, with the threshold its yes/no verdict reads its probability against.

    The question's instructions are still the authored template, rendered against memory when the step
    runs. The threshold is the operator's policy, so it travels beside the question rather than in it,
    and a question of another kind never carries one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: JudgmentQuestion
    threshold: float | None = None


class _AskedJudgment(NamedTuple):
    """What one request to the judging model was and returned: the evidence, the questions as asked, and their outcomes by key."""

    prompt: JudgmentPrompt
    questions: dict[str, JudgmentQuestion]
    outcomes: dict[str, JudgmentOutcome]


def judgment_setting_of_choice(*, judgment_choice: JudgmentModelChoice | None = None, pipe_code: str | None = None) -> JudgmentSetting:
    """The deck chain for a judgment: the step's own model, else the deck's default, as a setting.

    The deck serves no judgment model by default, so when the step names none and the deck names no
    default either, there is nothing to resolve: that is `JudgmentModelMissingError`, the same refusal
    the operator raises when its method loads. The setting's model is still the handle the deck names,
    which no backend may serve on this boot.
    """
    model_deck = get_model_deck()
    resolved_choice = judgment_choice or model_deck.judgment_choice_default
    if resolved_choice is None:
        raise JudgmentModelMissingError(pipe_code=pipe_code)
    return model_deck.get_judgment_setting(judgment_choice=resolved_choice)


def served_judgment_model(*, model_handle: str) -> InferenceModelSpec | None:
    """The spec of the judgment model a handle resolves to on this boot, `None` when no backend serves one.

    The deck answers `None` for an alias or a handle it does not serve, but raises for a waterfall none of
    whose models it serves, or whose fallbacks are disabled: here the two mean the same thing.
    """
    try:
        return get_model_deck().get_optional_inference_model(model_handle=model_handle, model_type=ModelType.JUDGMENT)
    except ModelNotFoundError:
        return None


def resolve_judgment_setting(
    *, judgment_choice: JudgmentModelChoice | None = None, pipe_code: str | None = None, is_dry: bool = False
) -> JudgmentSetting:
    """The deck chain for a judgment, then handle resolution.

    The returned setting is pinned to the *resolved* handle, so it doubles as a distributed run's
    routing key. A dry run calls no judging worker, so a model the deck names that no backend serves on
    this boot, as when its backend is disabled, keeps the deck's handle.
    """
    model_deck = get_model_deck()
    judgment_setting = judgment_setting_of_choice(judgment_choice=judgment_choice, pipe_code=pipe_code)
    if is_dry and served_judgment_model(model_handle=judgment_setting.model) is None:
        return judgment_setting

    inference_model = model_deck.get_required_inference_model(model_handle=judgment_setting.model, model_type=ModelType.JUDGMENT)
    # Pinned as a reference that parses back to the resolved handle, whatever its spelling, since every lookup reads it again.
    resolved_handle = write_model_handle(name=inference_model.name)
    if resolved_handle != judgment_setting.model:
        judgment_setting = judgment_setting.model_copy(update={"model": resolved_handle})
    return judgment_setting


async def run_judgment(
    *,
    memory: WorkingMemory,
    prompt_content: UserPromptContent,
    question: JudgmentQuestion,
    judgment_setting: JudgmentSetting,
    concept: Concept,
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
    templating_style: TemplatingStyle,
    threshold: float | None = None,
    result_name: str | None = None,
    result_code: str | None = None,
) -> JudgmentResult:
    """A whole judgment step asking one question: assemble the evidence, render the question, judge, read the verdict, store.

    The evidence is assembled as a PipeLLM's user prompt is, its images and documents numbered into
    `[Image N]` and `[Document N]` tokens. The question arrives as the cogt question with its
    instructions still a template, rendered here against memory as a `BASIC` template. The judgment
    itself goes through the same content-generation seam as every other leaf — direct inline, an
    activity when in-workflow, or a dry mock — so it is replay-safe under a distributed orchestrator.

    A refusal is the worker's outcome, and this step's policy for it is to fail: one question has
    nowhere to leave its verdict absent, so it raises `JudgmentRefusedError`, a content error naming
    the step and the model.

    The content stored is the verdict native's own class, never the output concept's: a concept
    refining `Choice` has no structure of its own, so its content is a `ChoiceContent`, stored under the
    refining concept as every operator stores a refinement.
    """
    with job_metadata.log_context():
        asked_judgment = await _ask_judgment(
            memory=memory,
            prompt_content=prompt_content,
            questions={JUDGMENT_QUESTION_KEY: question},
            judgment_setting=judgment_setting,
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            templating_style=templating_style,
        )
        asked_question = asked_judgment.questions[JUDGMENT_QUESTION_KEY]
        outcome = asked_judgment.outcomes[JUDGMENT_QUESTION_KEY]
        if isinstance(outcome, JudgmentRefusal):
            raise JudgmentRefusedError(pipe_code=job_metadata.pipe_code, model_handle=judgment_setting.model)
        content, threshold_applied = make_verdict_content(
            question=asked_question, answer=outcome, threshold=threshold, is_dry=cogt_run_params.run_mode.is_dry
        )
        if threshold_applied is False:
            log.warning(
                "A judgment's model reported no probability, and its own verdict stands",
                fields={"pipe_code": job_metadata.pipe_code, "threshold": threshold, "model_handle": judgment_setting.model},
            )
        return JudgmentResult(
            memory=store_result(memory=memory, concept=concept, content=content, result_name=result_name, result_code=result_code),
            content=content,
            prompt=asked_judgment.prompt,
            rendered_question=asked_question.instructions,
            judgment_setting=judgment_setting,
            answer=outcome,
            threshold_applied=threshold_applied,
        )


async def run_multi_judgment(
    *,
    memory: WorkingMemory,
    prompt_content: UserPromptContent,
    questions: dict[str, AskedQuestion],
    judgment_setting: JudgmentSetting,
    concept: Concept,
    output_class: type[StuffContent],
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
    templating_style: TemplatingStyle,
    result_name: str | None = None,
    result_code: str | None = None,
) -> MultiJudgmentResult:
    """A whole judgment step asking several questions over one evidence, in one request, and filling a structure with their verdicts.

    The evidence is assembled and each question rendered as `run_judgment` does, and every question goes
    in one job keyed by its name, which is also the name of the field of `output_class` holding its
    verdict. The caller resolves `output_class`, the structure class of the output concept, and hands it
    down, as PipeLLM's object path does, since the kernel does not read the concept library: its fields
    must be exactly the questions' names, which `JudgmentOutputFieldsError` refuses before the judging
    model is called. Each answer becomes its verdict native under the single form's rules, the question's
    own threshold deciding a yes/no verdict.

    A refusal leaves its question's field absent when that field may hold nothing, being neither
    required nor given a default, which is logged and recorded in the result's `judgments`. Any other
    refused question raises `JudgmentRefusedError`, a content error naming the step, the model and the
    question: leaving a defaulted field out would fill in its default, a verdict nobody gave. A dry run
    answers every question and never refuses.
    """
    with job_metadata.log_context():
        _check_questions_are_the_output_fields(question_names=list(questions), output_class=output_class)
        asked_judgment = await _ask_judgment(
            memory=memory,
            prompt_content=prompt_content,
            questions={question_name: asked_question.question for question_name, asked_question in questions.items()},
            judgment_setting=judgment_setting,
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            templating_style=templating_style,
        )
        field_values: dict[str, object] = {}
        judgments: dict[str, QuestionJudgment] = {}
        for question_name, asked_question in questions.items():
            question = asked_judgment.questions[question_name]
            outcome = asked_judgment.outcomes[question_name]
            if isinstance(outcome, JudgmentRefusal):
                if not _may_be_left_absent(field_info=output_class.model_fields[question_name]):
                    raise JudgmentRefusedError(pipe_code=job_metadata.pipe_code, model_handle=judgment_setting.model, question_name=question_name)
                log.warning(
                    "A judgment's model declined a question, and its field is left absent",
                    fields={"pipe_code": job_metadata.pipe_code, "model_handle": judgment_setting.model, "judgment_question": question_name},
                )
                judgments[question_name] = QuestionJudgment(rendered_question=question.instructions, outcome=outcome)
                continue
            verdict, threshold_applied = make_verdict_content(
                question=question, answer=outcome, threshold=asked_question.threshold, is_dry=cogt_run_params.run_mode.is_dry
            )
            if threshold_applied is False:
                log.warning(
                    "A judgment's model reported no probability, and its own verdict stands",
                    fields={
                        "pipe_code": job_metadata.pipe_code,
                        "threshold": asked_question.threshold,
                        "model_handle": judgment_setting.model,
                        "judgment_question": question_name,
                    },
                )
            # Handed over as plain data, so a field typed by a concept refining the verdict native, whose class
            # subclasses the native's, is built as that class rather than refusing the native's instance.
            field_values[question_name] = verdict.model_dump()
            judgments[question_name] = QuestionJudgment(rendered_question=question.instructions, outcome=outcome, threshold_applied=threshold_applied)
        content = output_class.model_validate(field_values)
        return MultiJudgmentResult(
            memory=store_result(memory=memory, concept=concept, content=content, result_name=result_name, result_code=result_code),
            content=content,
            prompt=asked_judgment.prompt,
            judgment_setting=judgment_setting,
            judgments=judgments,
        )


def _may_be_left_absent(*, field_info: FieldInfo) -> bool:
    """Whether a field may hold nothing, the rule a declared structure field follows: neither required nor given a default.

    Leaving such a field out gives it `None`, and it is the only kind whose default is `None`: a required
    field has no default at all, and a field given a default factory has none of its own either.
    """
    return field_info.default is None


def _check_questions_are_the_output_fields(*, question_names: list[str], output_class: type[StuffContent]) -> None:
    """Refuse an output class whose fields are not exactly the questions' names, naming every name on either side."""
    field_names = list(output_class.model_fields)
    unasked_fields = [field_name for field_name in field_names if field_name not in question_names]
    homeless_questions = [question_name for question_name in question_names if question_name not in field_names]
    if not unasked_fields and not homeless_questions:
        return
    complaints: list[str] = []
    if unasked_fields:
        complaints.append(f"no question answers its fields {', '.join(repr(field_name) for field_name in unasked_fields)}")
    if homeless_questions:
        complaints.append(f"it has no field for the questions {', '.join(repr(question_name) for question_name in homeless_questions)}")
    msg = (
        f"A judgment asking several questions fills the field of each question's name, and the output class '{output_class.__name__}' "
        f"does not hold exactly the questions' fields: {'; '.join(complaints)}."
    )
    raise JudgmentOutputFieldsError(msg)


async def _ask_judgment(
    *,
    memory: WorkingMemory,
    prompt_content: UserPromptContent,
    questions: dict[str, JudgmentQuestion],
    judgment_setting: JudgmentSetting,
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
    templating_style: TemplatingStyle,
) -> _AskedJudgment:
    """One request to the judging model: the evidence assembled, every question rendered as a `BASIC` template, all sent in one job."""
    with job_metadata.log_context():
        assembled_prompt = await assemble_user_prompt(prompt_content=prompt_content, context_provider=memory, templating_style=templating_style)
        judgment_prompt = JudgmentPrompt(text=assembled_prompt.text, images=assembled_prompt.images, documents=assembled_prompt.documents)
        context = memory.generate_context()
        asked_questions: dict[str, JudgmentQuestion] = {}
        for question_key, question in questions.items():
            rendered_question = await render_template(
                template=question.instructions,
                category=TemplateCategory.BASIC,
                context=context,
                templating_style=templating_style,
            )
            asked_questions[question_key] = question.model_copy(update={"instructions": rendered_question})
        judgment_assignment = JudgmentAssignment(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            prompt=judgment_prompt,
            questions=asked_questions,
            judgment_setting=judgment_setting,
        )
        outcomes = await get_content_generator().make_judgment_answers(judgment_assignment=judgment_assignment)
        return _AskedJudgment(prompt=judgment_prompt, questions=asked_questions, outcomes=outcomes)


def make_verdict_content(
    *, question: JudgmentQuestion, answer: JudgmentAnswer, threshold: float | None, is_dry: bool
) -> tuple[StuffContent, bool | None]:
    """The verdict native an answer translates to, and what became of a declared threshold.

    A yes/no answer with a probability is decided by it against the threshold, inclusive, the default
    standing in when none is declared; one without a probability keeps its own verdict, and a declared
    threshold then had nothing to work on, which a live run reports and a dry run, whose answers carry
    no probability by construction, does not. A rating takes the label of the level it names off the
    scale the question declared, since no backend reports one, and its distribution is keyed by the
    level index written as text, the one place that conversion happens. Nothing absent is synthesised.
    """
    match answer:
        case YesNoAnswer():
            if answer.probability is not None:
                yes_no = answer.probability >= (threshold if threshold is not None else DEFAULT_YES_NO_THRESHOLD)
                threshold_applied = True if threshold is not None else None
                return YesNoContent(yes_no=yes_no, probability=answer.probability), threshold_applied
            if answer.yes_no is None:
                # YesNoAnswer's own validator refuses an answer carrying neither, so a validated answer
                # never reaches this; it is stated for the type checker, which cannot see a validator.
                msg = "Judgment worker answered a yes/no question with neither a probability nor a verdict"
                raise JudgmentAnswerMismatchError(msg)
            threshold_applied = False if threshold is not None and not is_dry else None
            return YesNoContent(yes_no=answer.yes_no), threshold_applied
        case ChoiceAnswer():
            return ChoiceContent(choice=answer.choice, confidence=answer.confidence, probabilities=answer.probabilities), None
        case RatingAnswer():
            probabilities = (
                {str(level): probability for level, probability in answer.probabilities.items()} if answer.probabilities is not None else None
            )
            return RatingContent(
                level=answer.level,
                label=_declared_label(question=question, level=answer.level),
                confidence=answer.confidence,
                probabilities=probabilities,
                position=answer.position,
            ), None


def _declared_label(*, question: JudgmentQuestion, level: int) -> str | None:
    """The label the question's scale declares for a level, `None` when the scale declares none.

    The worker checked that the answer's kind is its question's and that its level is on the scale,
    so the two refusals here are stated for the type checker, which cannot see that check.
    """
    if not isinstance(question, RatingQuestion):
        msg = f"A rating answer came back for a {question.kind} question"
        raise JudgmentAnswerMismatchError(msg)
    if not 0 <= level < len(question.levels):
        msg = f"A rating answer names level {level}, which a scale of {len(question.levels)} levels does not hold"
        raise JudgmentAnswerMismatchError(msg)
    return question.levels[level].label
