"""Judgment operator semantics: deck resolution, question rendering, the material, the verdict, memory write-back.

These are the functions the interpreter's `PipeJudge` calls, and the ones a programmatic caller
invokes on a `RuntimeBoot`-only process. They read the runtime hub for the services a runtime boot
stands up (the model deck, the content generator) and take everything else as an explicit argument.

A judgment is asked over **material**: the step's inputs by name. Every input that is not a file is a
member of a JSON state, its value read off the content's class; every image or document travels beside
the state, keyed by the input's name, as the prompt images and documents an LLM prompt carries. The
dispatch is on the content's class rather than on a concept, because the kernel may not import the
concept library.
"""

from typing import Any

from pipelex import log
from pipelex.cogt.content_generation.assignment_models import JudgmentAssignment
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.document.prompt_document import PromptDocument
from pipelex.cogt.document.prompt_document_factory import PromptDocumentFactory
from pipelex.cogt.exceptions import JudgmentAnswerMismatchError, JudgmentModelMissingError, ModelNotFoundError
from pipelex.cogt.image.prompt_image import PromptImage
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.judgment.judgment_models import (
    ChoiceAnswer,
    JudgmentAnswer,
    JudgmentQuestion,
    JudgmentState,
    RatingAnswer,
    YesNoAnswer,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentModelChoice, JudgmentSetting
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.choice_content import ChoiceContent
from pipelex.core.stuffs.date_content import DateContent
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.json_content import JSONContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.rating_content import RatingContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.core.stuffs.time_content import TimeContent
from pipelex.core.stuffs.yes_no_content import YesNoContent
from pipelex.kernel.judgment_results import JudgmentResult
from pipelex.kernel.memory_ops import store_result
from pipelex.runtime_hub import get_content_generator, get_model_deck
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.templating.templating_style import TemplatingStyle

# The one question a step asks travels under this key: the batch-first contract needs a key, and
# nothing reads it but the answer lookup below.
JUDGMENT_QUESTION_KEY = "question"

# A yes/no verdict reads its reported probability against this when the step declares no threshold.
DEFAULT_YES_NO_THRESHOLD = 0.5


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
    this boot, as on a keyless boot that skipped the backend whose key is unset, keeps the deck's handle.
    """
    model_deck = get_model_deck()
    judgment_setting = judgment_setting_of_choice(judgment_choice=judgment_choice, pipe_code=pipe_code)
    if is_dry and served_judgment_model(model_handle=judgment_setting.model) is None:
        return judgment_setting

    inference_model = model_deck.get_required_inference_model(model_handle=judgment_setting.model, model_type=ModelType.JUDGMENT)
    if inference_model.name != judgment_setting.model:
        judgment_setting = judgment_setting.model_copy(update={"model": inference_model.name})
    return judgment_setting


async def run_judgment(
    *,
    memory: WorkingMemory,
    question: JudgmentQuestion,
    input_names: list[str],
    judgment_setting: JudgmentSetting,
    concept: Concept,
    job_metadata: JobMetadata,
    cogt_run_params: CogtRunParams,
    templating_style: TemplatingStyle,
    threshold: float | None = None,
    result_name: str | None = None,
    result_code: str | None = None,
) -> JudgmentResult:
    """A whole judgment step: render the question, gather the material, judge, read the verdict, store.

    The question arrives as the cogt question with its instructions still a template, rendered here
    against memory as a search renders its query. The judgment itself goes through the same
    content-generation seam as every other leaf — direct inline, an activity when in-workflow, or a dry
    mock — so it is replay-safe under a distributed orchestrator.

    The content stored is the verdict native's own class, never the output concept's: a concept
    refining `Choice` has no structure of its own, so its content is a `ChoiceContent`, stored under the
    refining concept as every operator stores a refinement.
    """
    with job_metadata.log_context():
        rendered_question = await render_template(
            template=question.instructions,
            category=TemplateCategory.BASIC,
            context=memory.generate_context(),
            templating_style=templating_style,
        )
        asked_question = question.model_copy(update={"instructions": rendered_question})
        state, images, documents = build_judgment_material(memory=memory, input_names=input_names)
        judgment_assignment = JudgmentAssignment(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            state=state,
            images=images,
            documents=documents,
            questions={JUDGMENT_QUESTION_KEY: asked_question},
            judgment_setting=judgment_setting,
        )
        answers = await get_content_generator().make_judgment_answers(judgment_assignment=judgment_assignment)
        answer = answers[JUDGMENT_QUESTION_KEY]
        content, threshold_applied = make_verdict_content(answer=answer, threshold=threshold, is_dry=cogt_run_params.run_mode.is_dry)
        if threshold_applied is False:
            log.warning(
                f"Judgment '{job_metadata.pipe_code or 'unnamed step'}' declares a threshold of {threshold}, but model "
                f"'{judgment_setting.model}' reported no probability, so its own verdict stands."
            )
        return JudgmentResult(
            memory=store_result(memory=memory, concept=concept, content=content, result_name=result_name, result_code=result_code),
            content=content,
            rendered_question=rendered_question,
            judgment_setting=judgment_setting,
            answer=answer,
            threshold_applied=threshold_applied,
        )


def build_judgment_material(
    *,
    memory: WorkingMemory,
    input_names: list[str],
) -> tuple[JudgmentState, dict[str, list[PromptImage]], dict[str, list[PromptDocument]]]:
    """The state and the files a judgment is asked over, one entry per input, keyed by its declared name.

    An input name is a plain name, so each entry is one whole value: the step's material holds exactly
    what it declares, and a field reaches it only when the calling sequence binds it under a name of its
    own. An optional input that holds no value, whether its absence was recorded or it was never written, is
    left out rather than sent as a null: a required input with no value never reaches the step, whose
    presence scan refuses it. An image or a document, or a list of either, goes to the file channel; every
    other input is a member of the state. An image nested inside a structured input is part of that input's
    JSON, its URL as text, which is the author's concern.
    """
    state: JudgmentState = {}
    images: dict[str, list[PromptImage]] = {}
    documents: dict[str, list[PromptDocument]] = {}
    for input_name in input_names:
        stuff = memory.get_optional_stuff(name=input_name)
        if stuff is None:
            continue
        content: StuffContent = stuff.content
        if prompt_images := _prompt_images(content=content):
            images[input_name] = prompt_images
        elif prompt_documents := _prompt_documents(content=content):
            documents[input_name] = prompt_documents
        else:
            state[input_name] = material_value(content=content)
    return state, images, documents


def material_value(*, content: StuffContent) -> Any:
    """The JSON value a content is judged as: the reading a caller would write for it.

    Text (and every refinement of it) is its string, a number its number, a yes/no its boolean, a date
    or a time its ISO string, a JSON object itself, a list the array of its items' values, and every
    other content — a choice, a rating, any structure — its JSON object without its absent members.
    """
    match content:
        case TextContent():
            return content.text
        case NumberContent():
            return content.number
        case YesNoContent():
            return content.yes_no
        case DateContent() | TimeContent():
            return content.rendered_plain()
        case JSONContent():
            return content.json_obj
        case ListContent():
            return [material_value(content=item) for item in content.items]
        case _:
            # Serialized as what each field holds rather than as its declared type, so a field typed as the
            # content base keeps the fields of the subclass a run put there.
            return content.model_dump(mode="json", exclude_none=True, serialize_as_any=True)


def _prompt_images(*, content: StuffContent) -> list[PromptImage] | None:
    image_contents: list[ImageContent]
    match content:
        case ImageContent():
            image_contents = [content]
        case ListContent() if content.items and all(isinstance(item, ImageContent) for item in content.items):
            image_contents = [item for item in content.items if isinstance(item, ImageContent)]
        case _:
            return None
    return [PromptImageFactory.make_prompt_image(uri=image.url, mime_type=image.mime_type) for image in image_contents]


def _prompt_documents(*, content: StuffContent) -> list[PromptDocument] | None:
    document_contents: list[DocumentContent]
    match content:
        case DocumentContent():
            document_contents = [content]
        case ListContent() if content.items and all(isinstance(item, DocumentContent) for item in content.items):
            document_contents = [item for item in content.items if isinstance(item, DocumentContent)]
        case _:
            return None
    return [PromptDocumentFactory.make_prompt_document(uri=document.url, mime_type=document.mime_type) for document in document_contents]


def make_verdict_content(*, answer: JudgmentAnswer, threshold: float | None, is_dry: bool) -> tuple[StuffContent, bool | None]:
    """The verdict native an answer translates to, and what became of a declared threshold.

    A yes/no answer with a probability is decided by it against the threshold, inclusive, the default
    standing in when none is declared; one without a probability keeps its own verdict, and a declared
    threshold then had nothing to work on, which a live run reports and a dry run, whose answers carry
    no probability by construction, does not. A rating's distribution is keyed by the level index
    written as text, the one place that conversion happens. Nothing absent is synthesised.
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
            return RatingContent(level=answer.level, confidence=answer.confidence, probabilities=probabilities, position=answer.position), None
