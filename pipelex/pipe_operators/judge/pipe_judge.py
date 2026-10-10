from typing import Any, Literal

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
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.interpreter_hub import get_concept_library, get_native_concept
from pipelex.kernel.judgment_ops import judgment_setting_of_choice, resolve_judgment_setting, run_judgment, served_judgment_model
from pipelex.kernel.prompt_assembly import UserPromptContent
from pipelex.kernel.prompt_references import DocumentReference, ImageReference
from pipelex.kernel.templating_style_ops import resolve_templating_style
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


class PipeJudge(PipeOperator[PipeJudgeOutput]):
    """Asks a judging model one closed question about the evidence its prompt presents, and stores the verdict native it answers with.

    `prompt_content` is the evidence: the prompt's template and the images and documents it references,
    assembled when the step runs exactly as a PipeLLM's user prompt is. `judgment_question` is the cogt
    question with its instructions still the authored template, so the kernel renders it against memory
    when the step runs; its kind decides the verdict native. The question presents no file, so the
    image and document references the factory found in it are held only for the load to refuse them.
    """

    type: Literal["PipeJudge"] = "PipeJudge"
    judgment_choice: JudgmentModelChoice | None
    prompt_content: UserPromptContent
    judgment_question: JudgmentQuestion
    question_image_references: list[ImageReference] | None = None
    question_document_references: list[DocumentReference] | None = None
    threshold: float | None = None

    @property
    def judgment_kind(self) -> JudgmentKind:
        return self.judgment_question.kind

    @property
    def question_blueprint(self) -> TemplateBlueprint:
        return TemplateBlueprint(template=self.judgment_question.instructions, category=TemplateCategory.BASIC)

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @override
    def required_variables(self) -> set[str]:
        full_paths = self.prompt_content.template.required_variables() | self.question_blueprint.required_variables()
        return {get_root_from_dotted_path(path) for path in full_paths if not path.startswith("_")}

    @override
    def validate_inputs_static(self):
        if self.judgment_choice is not None:
            with self.locating_model_choice(field_name="model"):
                check_judgment_choice_with_deck(judgment_choice=self.judgment_choice)

        # Only the prompt presents files: a question is sent as plain text, so an image or a document it
        # read would reach the model as a dangling token naming no file.
        question_file_paths = [
            *(image_reference.variable_path for image_reference in self.question_image_references or []),
            *(document_reference.variable_path for document_reference in self.question_document_references or []),
        ]
        if question_file_paths:
            quoted_paths = ", ".join(f"'{variable_path}'" for variable_path in question_file_paths)
            msg = (
                f"PipeJudge '{self.code}' reads {quoted_paths} in its question, which is an image or a document, and only the prompt "
                "presents files to the judging model: read it in `prompt`, and ask about it in `question`."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                domain_code=self.domain_code,
                pipe_code=self.code,
                variable_names=question_file_paths,
            )

        # Template lints: no private names, and every reference to a declared-optional input guarded (D7).
        question_blueprint = self.question_blueprint
        for template_blueprint, template_label in [(self.prompt_content.template, "prompt"), (question_blueprint, "question")]:
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
        """The output agrees with the question's kind: its verdict native, or a concept refining it.

        `Dynamic` is compatible with every concept, but a judgment's verdict is always its kind's native,
        so a `Dynamic` output is refused like any other that is not that native.
        """
        verdict_native = verdict_native_for_kind(judgment_kind=self.judgment_kind)
        if not NativeConceptCode.is_dynamic_concept(concept_code=self.output.concept.code) and get_concept_library().is_compatible(
            tested_concept=self.output.concept,
            wanted_concept=get_native_concept(native_concept=verdict_native),
            strict=True,
        ):
            return
        msg = (
            f"This PipeJudge {_kind_declaration(judgment_kind=self.judgment_kind)}: its output must be `{verdict_native}` "
            f"or a concept refining it, and it declares `{self.output.concept.concept_ref}`."
        )
        raise PipeValidationError(
            message=msg,
            error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
            domain_code=self.domain_code,
            pipe_code=self.code,
            provided_concept_code=self.output.concept.concept_ref,
            required_concept_codes=[verdict_native.concept_ref],
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
        judgment_result = await run_judgment(
            memory=working_memory,
            prompt_content=self.prompt_content,
            question=self.judgment_question,
            judgment_setting=judgment_setting,
            concept=self.output.concept,
            job_metadata=job_metadata,
            cogt_run_params=pipe_run_params.cogt_run_params,
            # No authored style on this operator: its prompt and question templates take the runtime
            # default, the same one an LLM pipe that declares nothing gets.
            templating_style=resolve_templating_style(authored=None),
            threshold=self.threshold,
            result_name=output_name,
        )

        # Capture execution data for the graph tracer. The raw answer rides along because it carries
        # what the verdict native's rendering does not show, such as a choice's whole distribution.
        judgment_prompt = judgment_result.prompt
        execution_data_dict: dict[str, Any] = {
            "rendered_prompt": judgment_prompt.text,
            "nb_prompt_images": len(judgment_prompt.images),
            "nb_prompt_documents": len(judgment_prompt.documents),
            "rendered_question": judgment_result.rendered_question,
            "resolved_model": judgment_result.judgment_setting.model,
            "judgment_kind": self.judgment_kind.value,
            "answer": judgment_result.answer.model_dump(mode="json", exclude_none=True),
        }
        if self.threshold is not None:
            execution_data_dict["threshold"] = self.threshold
        if judgment_result.threshold_applied is not None:
            execution_data_dict["threshold_applied"] = judgment_result.threshold_applied

        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
        return PipeJudgeOutput(
            working_memory=judgment_result.memory,
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
