from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import override

from pipelex.cogt.judgment.judgment_models import (
    ChoiceQuestion,
    JudgmentKind,
    JudgmentQuestion,
    RatingLevel,
    RatingQuestion,
    YesNoCriteria,
    YesNoQuestion,
)
from pipelex.cogt.judgment.judgment_setting import JudgmentModelChoice
from pipelex.cogt.models.model_deck_check import check_judgment_choice_with_deck
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.interpreter_hub import get_concept_library, get_native_concept
from pipelex.kernel.judgment_ops import (
    AskedQuestion,
    judgment_setting_of_choice,
    resolve_judgment_setting,
    run_judgment,
    run_multi_judgment,
    served_judgment_model,
)
from pipelex.kernel.prompt_assembly import UserPromptContent
from pipelex.kernel.prompt_references import DocumentReference, ImageReference
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.pipe_controllers.binding.binding_concept_resolvers import LibraryConceptWalkResolver, library_concept_key
from pipelex.pipe_controllers.binding.binding_derivation import BindingValueKind, ConceptShape, WalkableField
from pipelex.pipe_machinery.template_guard_lint import lint_authored_template
from pipelex.pipe_operators.judge.exceptions import PipeJudgeInputCapabilityError
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata
from pipelex.tools.jinja2.template_category import TemplateCategory
from pipelex.tools.misc.string_utils import get_root_from_dotted_path
from pipelex.validation_error_types import PipeValidationErrorType


class PipeJudgeOutput(PipeOutput):
    pass


def verdict_native_for_kind(*, judgment_kind: JudgmentKind) -> NativeConceptCode:
    """The verdict native a question of this kind produces."""
    match judgment_kind:
        case JudgmentKind.YES_NO:
            return NativeConceptCode.YES_NO
        case JudgmentKind.CHOICE:
            return NativeConceptCode.CHOICE
        case JudgmentKind.RATING:
            return NativeConceptCode.RATING


def _kind_declaration(*, judgment_kind: JudgmentKind) -> str:
    match judgment_kind:
        case JudgmentKind.YES_NO:
            return "declares neither `options` nor `levels`, so it asks a yes/no question"
        case JudgmentKind.CHOICE:
            return "declares `options`, so it asks a choice question"
        case JudgmentKind.RATING:
            return "declares `levels`, so it asks a rating question"


def _kind_question(*, judgment_kind: JudgmentKind) -> str:
    match judgment_kind:
        case JudgmentKind.YES_NO:
            return "a yes/no question"
        case JudgmentKind.CHOICE:
            return "a choice question"
        case JudgmentKind.RATING:
            return "a rating question"


def _holds_verdict(*, concept: Concept, verdict_native: NativeConceptCode) -> bool:
    """Whether a concept holds the verdict native: the native itself or a concept refining it, strictly compatible.

    `Dynamic` is compatible with every concept, but a judgment's verdict is always its kind's native, so a
    `Dynamic` concept never holds one.
    """
    if NativeConceptCode.is_dynamic_concept(concept_code=concept.code):
        return False
    return get_concept_library().is_compatible(tested_concept=concept, wanted_concept=get_native_concept(native_concept=verdict_native), strict=True)


class PipeJudgeQuestion(BaseModel):
    """One question a PipeJudge asks, as the operator holds it: the cogt question and the policy the operator reads its verdict with.

    `judgment_question` is the cogt question with its instructions still the authored template, so the
    kernel renders it against memory when the step runs; its kind decides the verdict native. A yes/no
    question's `threshold` is the operator's policy, so it travels beside the question. The question
    presents no file, so the image and document references the factory found in it are held only for the
    load to refuse them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    judgment_question: JudgmentQuestion
    threshold: float | None = None
    image_references: list[ImageReference] | None = None
    document_references: list[DocumentReference] | None = None

    @property
    def judgment_kind(self) -> JudgmentKind:
        return self.judgment_question.kind

    @property
    def template_blueprint(self) -> TemplateBlueprint:
        return TemplateBlueprint(template=self.judgment_question.instructions, category=TemplateCategory.BASIC)

    @property
    def file_variable_paths(self) -> list[str]:
        """The variables the question reads that hold an image or a document, which it cannot present."""
        return [
            *(image_reference.variable_path for image_reference in self.image_references or []),
            *(document_reference.variable_path for document_reference in self.document_references or []),
        ]


class PipeJudge(PipeOperator[PipeJudgeOutput]):
    """Asks a judging model closed questions about the evidence its prompt presents, and stores the verdicts they answer with.

    `prompt_content` is the evidence: the prompt's template and the images and documents it references,
    assembled when the step runs exactly as a PipeLLM's user prompt is. A step asks exactly one of two
    ways: one `question`, whose verdict native is the output, or several `questions`, keyed by name, whose
    verdicts fill the output's structure, each in the field of its question's name.
    """

    type: Literal["PipeJudge"] = "PipeJudge"
    judgment_choice: JudgmentModelChoice | None
    prompt_content: UserPromptContent
    question: PipeJudgeQuestion | None = None
    questions: dict[str, PipeJudgeQuestion] | None = None

    @model_validator(mode="after")
    def _asks_one_question_or_several(self) -> Self:
        if self.question is not None and self.questions is not None:
            msg = f"PipeJudge '{self.code}' asks one question or several, and it was given both a single question and several."
            raise ValueError(msg)
        if self.question is None and not self.questions:
            msg = f"PipeJudge '{self.code}' asks one question or several, and it was given none."
            raise ValueError(msg)
        return self

    @property
    def labelled_questions(self) -> list[tuple[str, PipeJudgeQuestion]]:
        """Every question the step asks, with the words a message names it by: "question" alone, or "question 'name'" among several."""
        if self.questions is not None:
            return [(f"question '{question_name}'", question) for question_name, question in self.questions.items()]
        if self.question is not None:
            return [("question", self.question)]
        return []

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @override
    def required_variables(self) -> set[str]:
        full_paths = self.prompt_content.template.required_variables()
        for _, question in self.labelled_questions:
            full_paths |= question.template_blueprint.required_variables()
        return {get_root_from_dotted_path(path) for path in full_paths if not path.startswith("_")}

    @override
    def validate_inputs_static(self):
        if self.judgment_choice is not None:
            with self.locating_model_choice(field_name="model"):
                check_judgment_choice_with_deck(judgment_choice=self.judgment_choice)

        # Only the prompt presents files: a question is rendered against the raw context with no token
        # parameters, so an image or a document it read would be written into the question sent to the
        # vendor as the content's string form, such as its storage URL, rather than presented as a file.
        for question_label, question in self.labelled_questions:
            question_file_paths = question.file_variable_paths
            if not question_file_paths:
                continue
            quoted_paths = ", ".join(f"'{variable_path}'" for variable_path in question_file_paths)
            msg = (
                f"PipeJudge '{self.code}' reads {quoted_paths} in its {question_label}, which is an image or a document, and only the "
                "prompt presents files to the judging model: read it in `prompt`, and ask about it in the question."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                domain_code=self.domain_code,
                pipe_code=self.code,
                variable_names=question_file_paths,
            )

        # Template lints: no private names, and every reference to a declared-optional input guarded (D7).
        labelled_templates = [(self.prompt_content.template, "prompt")]
        labelled_templates.extend((question.template_blueprint, question_label) for question_label, question in self.labelled_questions)
        for template_blueprint, template_label in labelled_templates:
            lint_authored_template(
                pipe_code=self.code,
                domain_code=self.domain_code,
                inputs=self.inputs,
                template_source=template_blueprint.template,
                template_category=template_blueprint.category,
                template_label=template_label,
            )

    @override
    def validate_inputs_with_library(self):
        """Find the judging model, and refuse an image or a document the prompt presents that it does not read.

        The model is found when the method loads, so a step with no model to judge with, naming none
        where the deck names no default, is refused with `JudgmentModelMissingError` before a run spends
        anything: the deck serves no judgment model out of the box. The prompt presents the images and
        documents it reads to the model as files, and whether the model reads one is its own capability,
        stated in its spec's `inputs`: a model that does not is refused here, naming the variable and what
        it reads. Only what the prompt references is checked, never every declared input, since an input
        reaches the model only through a template. That needs the model's spec, which a boot that does not
        enable the model's backend does not hold, and neither does one serving none of a waterfall's
        models: the check is then left to the worker when the step runs. A keyless boot holds the spec: it
        keeps every enabled backend, whether or not its key is set.
        """
        with self.locating_model_choice(field_name="model"):
            judgment_setting = judgment_setting_of_choice(judgment_choice=self.judgment_choice, pipe_code=self.code)
        inference_model = served_judgment_model(model_handle=judgment_setting.model)
        if inference_model is None:
            return
        if self.prompt_content.image_references and not inference_model.is_vision_supported:
            raise PipeJudgeInputCapabilityError(
                pipe_code=self.code,
                variable_path=self.prompt_content.image_references[0].variable_path,
                file_kind="image",
                model_name=inference_model.name,
                model_inputs=inference_model.inputs,
            )
        if self.prompt_content.document_references and not inference_model.is_document_supported:
            raise PipeJudgeInputCapabilityError(
                pipe_code=self.code,
                variable_path=self.prompt_content.document_references[0].variable_path,
                file_kind="document",
                model_name=inference_model.name,
                model_inputs=inference_model.inputs,
            )

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        """The output agrees with what the step asks: one question's verdict native, or a structure holding every question's verdict.

        Asking one question, the output is its kind's verdict native or a concept refining it. Asking
        several, the output is a concept with a structure whose fields are exactly the question names,
        each holding one of its question's verdict native, or of a concept refining it.
        """
        if self.questions is not None:
            self._validate_output_holds_every_verdict(questions=self.questions)
            return
        if self.question is None:
            return
        judgment_kind = self.question.judgment_kind
        verdict_native = verdict_native_for_kind(judgment_kind=judgment_kind)
        if _holds_verdict(concept=self.output.concept, verdict_native=verdict_native):
            return
        msg = (
            f"This PipeJudge {_kind_declaration(judgment_kind=judgment_kind)}: its output must be `{verdict_native}` "
            f"or a concept refining it, and it declares `{self.output.concept.concept_ref}`."
        )
        raise self._inadequate_output_error(message=msg, required_concept_codes=[verdict_native.concept_ref])

    def _validate_output_holds_every_verdict(self, *, questions: dict[str, PipeJudgeQuestion]) -> None:
        """Refuse an output that is no structure, a question with no field, a field no question answers, and a field that cannot hold its verdict.

        The output's structure is read as the binding walk reads it, so a concept refining a structured
        concept offers the fields it inherits, and a structure that exists only as a Python class offers
        its class's fields.
        """
        concept_library = get_concept_library()
        output_ref = self.output.concept.concept_ref
        walkable_output = LibraryConceptWalkResolver(concept_library=concept_library).resolve_walkable_concept(
            concept_ref=library_concept_key(concept_library=concept_library, concept=self.output.concept)
        )
        match walkable_output.shape:
            case ConceptShape.STRUCTURE:
                pass
            case ConceptShape.VALUE | ConceptShape.NO_STRUCTURE:
                msg = (
                    "This PipeJudge asks several questions and fills a structure with one verdict per question, so its output must be a "
                    f"concept with a structure, and `{output_ref}` {walkable_output.shape_reason}."
                )
                raise self._inadequate_output_error(message=msg)
        for question_name in questions:
            if walkable_output.get_field(name=question_name) is None:
                msg = (
                    f"The question '{question_name}' has no field of `{output_ref}` to hold its verdict: a PipeJudge asking several "
                    f"questions fills the field named after each question, so add a field '{question_name}' to `{output_ref}`, or "
                    "name the question after one of its fields."
                )
                raise self._inadequate_output_error(message=msg)
        unasked_field_names = [field_name for field_name in walkable_output.field_names if field_name not in questions]
        if unasked_field_names:
            quoted_names = ", ".join(f"'{field_name}'" for field_name in unasked_field_names)
            field_words = "the field" if len(unasked_field_names) == 1 else "the fields"
            msg = (
                f"A PipeJudge asking several questions fills only the fields named after them, and `{output_ref}` has {field_words} "
                f"{quoted_names}, which no question answers and so could never be filled: ask a question of that name, or remove the "
                "field from the structure."
            )
            raise self._inadequate_output_error(message=msg)
        for question_name, question in questions.items():
            walkable_field = walkable_output.get_field(name=question_name)
            if walkable_field is not None:
                self._validate_field_holds_its_verdict(
                    output_ref=output_ref, question_name=question_name, question=question, walkable_field=walkable_field
                )

    def _validate_field_holds_its_verdict(
        self, *, output_ref: str, question_name: str, question: PipeJudgeQuestion, walkable_field: WalkableField
    ) -> None:
        """Refuse a field that cannot hold one verdict of its question's kind: a list, a plain value, or a concept other than the native's line."""
        verdict_native = verdict_native_for_kind(judgment_kind=question.judgment_kind)
        asks = _kind_question(judgment_kind=question.judgment_kind)
        remedy = f"declare it a field of type `concept` whose `concept_ref` names `{verdict_native.concept_ref}` or a concept refining it"
        held_concept: str
        if walkable_field.is_list:
            msg = (
                f"The field '{question_name}' of `{output_ref}` holds a list, and the question '{question_name}' produces one verdict: "
                f"{remedy}. To judge each item of a list, map the PipeJudge over it with a PipeBatch."
            )
            raise self._inadequate_output_error(message=msg, required_concept_codes=[verdict_native.concept_ref])
        match walkable_field.value_kind:
            case BindingValueKind.CONCEPT:
                field_concept_ref = walkable_field.concept_ref
                if field_concept_ref is not None and _holds_verdict(
                    concept=get_concept_library().get_required_concept(concept_ref=field_concept_ref), verdict_native=verdict_native
                ):
                    return
                held_concept = f"`{field_concept_ref}`" if field_concept_ref is not None else "no concept"
            case (
                BindingValueKind.TEXT
                | BindingValueKind.NUMBER
                | BindingValueKind.YES_NO
                | BindingValueKind.DATE
                | BindingValueKind.DATETIME
                | BindingValueKind.TIME
                | BindingValueKind.JSON
                | BindingValueKind.ANYTHING
            ):
                msg = (
                    f"The field '{question_name}' of `{output_ref}` holds a plain value rather than a concept, and the question "
                    f"'{question_name}' asks {asks}, whose verdict is a `{verdict_native.concept_ref}`: {remedy}."
                )
                raise self._inadequate_output_error(message=msg, required_concept_codes=[verdict_native.concept_ref])
            case BindingValueKind.UNDERIVABLE:
                msg = (
                    f"The field '{question_name}' of `{output_ref}` holds a value no concept describes, since "
                    f"{walkable_field.underivable_reason}, and the question '{question_name}' asks {asks}: {remedy}."
                )
                raise self._inadequate_output_error(message=msg, required_concept_codes=[verdict_native.concept_ref])
        msg = (
            f"The question '{question_name}' asks {asks}, so its field must hold `{verdict_native.concept_ref}` or a concept refining "
            f"it, and it holds {held_concept}."
        )
        raise self._inadequate_output_error(message=msg, required_concept_codes=[verdict_native.concept_ref])

    def _inadequate_output_error(self, *, message: str, required_concept_codes: list[str] | None = None) -> PipeValidationError:
        return PipeValidationError(
            message=message,
            error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
            domain_code=self.domain_code,
            pipe_code=self.code,
            provided_concept_code=self.output.concept.concept_ref,
            required_concept_codes=required_concept_codes,
        )

    @override
    async def _live_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeJudgeOutput:
        # Resolved per run into a local and never cached onto `self`, for the reason `pipe_llm.py`
        # states about its own settings.
        judgment_setting = resolve_judgment_setting(judgment_choice=self.judgment_choice, pipe_code=self.code, is_dry=pipe_run_params.run_mode.is_dry)
        # No authored style on this operator: its prompt and question templates take the runtime default,
        # the same one an LLM pipe that declares nothing gets.
        templating_style = resolve_templating_style(authored=None)
        execution_data_dict: dict[str, Any]
        result_memory: WorkingMemory
        if self.questions is not None:
            multi_result = await run_multi_judgment(
                memory=working_memory,
                prompt_content=self.prompt_content,
                questions={
                    question_name: AskedQuestion(question=question.judgment_question, threshold=question.threshold)
                    for question_name, question in self.questions.items()
                },
                judgment_setting=judgment_setting,
                concept=self.output.concept,
                # The kernel does not read the concept library, so the output's content class is resolved here and
                # handed down, as PipeLLM's object path does.
                output_class=get_concept_library().get_structure_class(concept=self.output.concept),
                job_metadata=job_metadata,
                cogt_run_params=pipe_run_params.cogt_run_params,
                templating_style=templating_style,
                result_name=output_name,
            )
            question_records: dict[str, dict[str, Any]] = {}
            for question_name, question in self.questions.items():
                judgment = multi_result.judgments[question_name]
                question_record: dict[str, Any] = {
                    "rendered_question": judgment.rendered_question,
                    "judgment_kind": question.judgment_kind,
                    "outcome": judgment.outcome.model_dump(mode="json", exclude_none=True),
                }
                if question.threshold is not None:
                    question_record["threshold"] = question.threshold
                if judgment.threshold_applied is not None:
                    question_record["threshold_applied"] = judgment.threshold_applied
                question_records[question_name] = question_record
            execution_data_dict = {
                "rendered_prompt": multi_result.prompt.text,
                "nb_prompt_images": len(multi_result.prompt.images),
                "nb_prompt_documents": len(multi_result.prompt.documents),
                "resolved_model": multi_result.judgment_setting.model,
                # Each question's raw outcome rides along, a refusal included, since a field left absent shows nothing.
                "questions": question_records,
            }
            result_memory = multi_result.memory
        elif self.question is not None:
            judgment_result = await run_judgment(
                memory=working_memory,
                prompt_content=self.prompt_content,
                question=self.question.judgment_question,
                judgment_setting=judgment_setting,
                concept=self.output.concept,
                job_metadata=job_metadata,
                cogt_run_params=pipe_run_params.cogt_run_params,
                templating_style=templating_style,
                threshold=self.question.threshold,
                result_name=output_name,
            )
            # The raw answer rides along because it carries what the verdict native's rendering does not
            # show, such as a choice's whole distribution.
            judgment_prompt = judgment_result.prompt
            execution_data_dict = {
                "rendered_prompt": judgment_prompt.text,
                "nb_prompt_images": len(judgment_prompt.images),
                "nb_prompt_documents": len(judgment_prompt.documents),
                "rendered_question": judgment_result.rendered_question,
                "resolved_model": judgment_result.judgment_setting.model,
                "judgment_kind": self.question.judgment_kind,
                "answer": judgment_result.answer.model_dump(mode="json", exclude_none=True),
            }
            if self.question.threshold is not None:
                execution_data_dict["threshold"] = self.question.threshold
            if judgment_result.threshold_applied is not None:
                execution_data_dict["threshold_applied"] = judgment_result.threshold_applied
            result_memory = judgment_result.memory
        else:
            msg = f"PipeJudge '{self.code}' asks no question, which its construction refuses."
            raise PipeValidationError(message=msg, domain_code=self.domain_code, pipe_code=self.code)

        # Capture execution data for the graph tracer.
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
        return PipeJudgeOutput(
            working_memory=result_memory,
            pipeline_run_id=job_metadata.run_metadata.pipeline_run_id,
        )

    @override
    async def _validate_before_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    @override
    async def _validate_after_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass


def make_judgment_question(
    *,
    question_template: str,
    options: dict[str, str] | None,
    levels: list[RatingLevel] | None,
    criteria: YesNoCriteria | None,
) -> JudgmentQuestion:
    """The cogt question frame for a step, its instructions the authored template, its kind read off the fields declared.

    An option declared with an empty description is undescribed, which the cogt question reads as `None`.
    """
    if options is not None:
        return ChoiceQuestion(instructions=question_template, options={key: description or None for key, description in options.items()})
    if levels is not None:
        return RatingQuestion(instructions=question_template, levels=levels)
    return YesNoQuestion(instructions=question_template, criteria=criteria)
