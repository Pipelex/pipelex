from typing import TYPE_CHECKING, Any, Literal

from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import iter_cause_chain
from pipelex.cogt.exceptions import LLMCompletionError
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting, LLMSettingChoices
from pipelex.cogt.models.model_deck_check import check_llm_choice_with_deck
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeRunError, PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.interpreter_hub import get_concept_library, get_native_concept, get_required_concept
from pipelex.kernel.llm_ops import (
    concrete_llm_model_handle,
    derive_templating_style,
    resolve_llm_setting_for_object,
    resolve_llm_setting_for_text,
    run_llm_object,
    run_llm_text,
)
from pipelex.pipe_machinery.template_guard_lint import lint_optional_input_guards
from pipelex.pipe_machinery.validation import is_input_used_by_variables, is_variable_satisfied_by_inputs
from pipelex.pipe_operators.llm.llm_prompt_blueprint import LLMPromptBlueprint
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import (
    PipeRunParams,
    output_multiplicity_to_apply,
)
from pipelex.runtime_hub import get_class_registry
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_param_key import PipeRunParamKey
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.cogt.llm.llm_prompt import LLMPrompt
    from pipelex.kernel.llm_results import StructuringPath


class PipeLLMOutput(PipeOutput):
    pass


class PipeLLM(PipeOperator[PipeLLMOutput]):
    type: Literal["PipeLLM"] = "PipeLLM"
    llm_prompt_spec: LLMPromptBlueprint
    llm_choices: LLMSettingChoices | None = None
    output_multiplicity: VariableMultiplicity | None = None

    @override
    def validate_inputs_static(self):
        if self.llm_choices:
            for llm_choice_ref in self.llm_choices.list_choice_references():
                check_llm_choice_with_deck(llm_choice=llm_choice_ref)

        needed_inputs = self.needed_inputs()
        required_variable_paths = self.required_variables()
        input_names = {input_name for input_name, _ in needed_inputs.items}

        # Check for unused inputs: declared in inputs but not used by any variable path
        for input_name in input_names:
            if not is_input_used_by_variables(input_name, variable_paths=required_variable_paths):
                msg = f"PipeLLM '{self.code}' has input '{input_name}' declared but it is not used in the prompt or system_prompt."
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    variable_names=[input_name],
                    explanation=f"Input '{input_name}' is declared in inputs but not referenced in prompt/system_prompt.",
                )

        # Check for missing inputs: variable paths in prompt/system_prompt not satisfied by any input
        for variable_path in required_variable_paths:
            if not is_variable_satisfied_by_inputs(variable_path, input_names=input_names):
                msg = f"PipeLLM '{self.code}' uses variable '{variable_path}' in prompt/system_prompt but it is not declared in inputs."
                raise PipeValidationError(
                    message=msg,
                    error_type=PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain_code=self.domain_code,
                    pipe_code=self.code,
                    variable_names=[variable_path],
                    explanation=f"Variable '{variable_path}' is used in prompt/system_prompt but not declared in inputs.",
                )

        # Guard-lint (D7): every reference to a declared-optional input must be guarded.
        for template_blueprint, template_label in [
            (self.llm_prompt_spec.prompt_blueprint, "prompt"),
            (self.llm_prompt_spec.system_prompt_blueprint, "system_prompt"),
        ]:
            if template_blueprint is None:
                continue
            lint_optional_input_guards(
                pipe_code=self.code,
                domain_code=self.domain_code,
                inputs=self.inputs,
                template_source=template_blueprint.template,
                template_category=template_blueprint.category,
                template_label=template_label,
            )

    @override
    def validate_inputs_with_library(self):
        pass

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        # TODO: generalize because there are other concepts PipeLLM can't generate, not just images,
        # and PipeLLM is not the only one with this kind of constraints

        # Allow Dynamic output concept as it's flexible and can represent anything
        if NativeConceptCode.is_dynamic_concept(concept_code=self.output.concept.code):
            return

        if get_concept_library().is_compatible(
            tested_concept=self.output.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.IMAGE),
        ):
            msg = (
                f"The output of the PipeLLM '{self.code}' cannot be compatible with the Image concept. "
                f"The output concept is '{self.output.concept.concept_ref}'. "
                "Use a PipeImgGen if you want to generate images. You can use a PipeLLM to generate the prompt for a PipeImgGen."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
            )

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        needed_inputs = InputStuffSpecsFactory.make_empty()

        for input_name, stuff_spec in self.inputs.items:
            needed_inputs.add_stuff_spec(
                variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity, presence=stuff_spec.presence
            )

        return needed_inputs

    @override
    def required_variables(self) -> set[str]:
        return {variable_name for variable_name in self.llm_prompt_spec.required_variables() if not variable_name.startswith("_")}

    def resolve_dynamic_output_stuff_spec(self, pipe_run_params: PipeRunParams) -> StuffSpec:
        """Return the `StuffSpec` to use for this run. When the pipe's declared output is
        `native.Dynamic`, the actual concept is resolved from the run params (override
        on `pipe_run_params.dynamic_output_concept_ref`, with a legacy fallback on
        `pipe_run_params.params[DYNAMIC_OUTPUT_CONCEPT]`, defaulting to `native.Text`)
        and returned in a copy of `self.output`. Otherwise returns `self.output` unchanged.

        Pure: never mutates `self`. The same pipe instance can therefore be reused across
        runs with different `dynamic_output_concept_ref` values without the first run's
        choice sticking.
        """
        # TODO: DYNAMIC_OUTPUT_CONCEPT should not be a key in `params`; promote to an
        # attribute on PipeRunParams and drop the params-key fallback.
        if self.output.concept.code != NativeConceptCode.DYNAMIC or self.output.concept.domain_code != SpecialDomain.NATIVE:
            return self.output
        output_concept_ref = pipe_run_params.dynamic_output_concept_ref or pipe_run_params.params.get(PipeRunParamKey.DYNAMIC_OUTPUT_CONCEPT)
        if not output_concept_ref:
            output_concept_ref = SpecialDomain.NATIVE + "." + NativeConceptCode.TEXT
        resolved_concept = get_required_concept(
            concept_ref=ConceptFactory.make_concept_ref_with_domain_from_concept_ref_or_code(
                domain_code=self.domain_code,
                concept_ref_or_code=output_concept_ref,
            ),
        )
        return self.output.model_copy(update={"concept": resolved_concept})

    @override
    async def _live_run_operator_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeLLMOutput:
        # interpret / unwrap the arguments
        output_stuff_spec = self.resolve_dynamic_output_stuff_spec(pipe_run_params=pipe_run_params)

        multiplicity_resolution = output_multiplicity_to_apply(
            base_multiplicity=self.output_multiplicity,
            override_multiplicity=pipe_run_params.output_multiplicity,
        )
        applied_output_multiplicity = multiplicity_resolution.resolved_multiplicity
        is_multiple_output = multiplicity_resolution.is_multiple_outputs_enabled
        fixed_nb_output = multiplicity_resolution.specific_output_count

        # Collect what LLM settings we have for this particular PipeLLM
        llm_for_text_choice: LLMModelChoice | None = None
        llm_for_object_choice: LLMModelChoice | None = None
        if self.llm_choices:
            llm_for_text_choice = self.llm_choices.for_text
            llm_for_object_choice = self.llm_choices.for_object

        # The deck chain and the style derivation are kernel semantics; the settings are derived per
        # run into locals and never cached onto `self`, because the pipe instance is the one the
        # library holds and hands out — a write-back would make its serialized form depend on run
        # order and shadow any later config/deck change with the first run's value.
        llm_setting_main: LLMSetting = resolve_llm_setting_for_text(llm_choice=llm_for_text_choice)
        llm_setting_for_object: LLMSetting = resolve_llm_setting_for_object(
            llm_choice=llm_for_object_choice,
            llm_choice_for_text=llm_for_text_choice,
        )
        # Both paths render under the *text* setting's style: it is the pipe's main model, and the
        # object path differs only in how the answer comes back, not in how the prompt is written.
        templating_style = derive_templating_style(llm_setting=llm_setting_main)

        llm_prompt_run_params = PipeRunParams.copy_by_injecting_multiplicity(
            pipe_run_params=pipe_run_params,
            applied_output_multiplicity=applied_output_multiplicity,
        )

        # Resolved here rather than inside the kernel: turning a concept into a class is a library's
        # business, and handing the class over is what spares the kernel a registry read.
        output_class = get_class_registry().get_required_subclass(
            name=output_stuff_spec.concept.structure_class_name,
            base_class=StuffContent,
        )
        prompt_content = self.llm_prompt_spec.to_prompt_content()
        rendered_llm_prompt: LLMPrompt
        structuring_path: StructuringPath

        # The library-backed text-vs-object dispatch stays here: the kernel's two entry points are
        # this fork made explicit, and answering it needs a loaded library.
        if (
            get_concept_library().is_compatible(
                tested_concept=output_stuff_spec.concept,
                wanted_concept=get_native_concept(NativeConceptCode.TEXT),
                strict=True,
            )
            and not is_multiple_output
        ):
            try:
                text_result = await run_llm_text(
                    memory=working_memory,
                    prompt_content=prompt_content,
                    llm_setting=llm_setting_main,
                    concept=output_stuff_spec.concept,
                    output_class=output_class,
                    job_metadata=job_metadata,
                    cogt_run_params=pipe_run_params.cogt_run_params,
                    templating_style=templating_style,
                    extra_params=llm_prompt_run_params.params,
                    result_name=output_name,
                    result_code=pipe_run_params.final_stuff_code,
                )
            except LLMCompletionError as exc:
                location = self._format_error_location(pipe_run_params=pipe_run_params)
                error_details = self._format_llm_error(exc=exc, settings=[llm_setting_main])
                msg = f"Error generating text with LLM {location}: {error_details}"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc
            except ValidationError as exc:
                location = self._format_error_location(pipe_run_params=pipe_run_params)
                error_details = format_pydantic_validation_error(exc)
                msg = f"Error generating text content in PipeLLM {location}: {error_details}"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc
            working_memory = text_result.memory
            rendered_llm_prompt = text_result.rendered_prompt
            structuring_path = text_result.structuring_path
        else:
            if is_multiple_output:
                log.verbose(f"PipeLLM generating {fixed_nb_output} output(s)" if fixed_nb_output else "PipeLLM generating a list of output(s)")
            else:
                log.verbose(f"PipeLLM generating a single object output, class name: '{output_stuff_spec.concept.structure_class_name}'")

            try:
                object_result = await run_llm_object(
                    memory=working_memory,
                    prompt_content=prompt_content,
                    llm_setting=llm_setting_for_object,
                    concept=output_stuff_spec.concept,
                    output_class=output_class,
                    job_metadata=job_metadata,
                    cogt_run_params=pipe_run_params.cogt_run_params,
                    is_multiple_output=is_multiple_output,
                    fixed_nb_output=fixed_nb_output,
                    templating_style=templating_style,
                    extra_params=llm_prompt_run_params.params,
                    result_name=output_name,
                    result_code=pipe_run_params.final_stuff_code,
                )
            except LLMCompletionError as exc:
                location = self._format_error_location(pipe_run_params=pipe_run_params)
                error_details = self._format_llm_error(exc=exc, settings=[llm_setting_for_object])
                what_failed = "list of objects" if is_multiple_output else "single object"
                msg = f"Error generating {what_failed} with direct method {location}: {error_details}"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc
            working_memory = object_result.memory
            rendered_llm_prompt = object_result.rendered_prompt
            structuring_path = object_result.structuring_path

        # Capture execution data for the graph tracer
        execution_data_dict: dict[str, Any] = {
            # Fully resolved, not `llm_setting_*.model`: the deck advances one hop, so a
            # preset lands on another alias and a DRY run could only ever report a
            # half-resolved handle. Resolving here makes the reported model identical
            # whether or not the pipe ran.
            "resolved_model": concrete_llm_model_handle(llm_setting_main.model),
            "resolved_model_for_object": concrete_llm_model_handle(llm_setting_for_object.model),
            "is_multiple_output": is_multiple_output,
            "rendered_system_prompt": rendered_llm_prompt.system_text,
            "rendered_user_prompt": rendered_llm_prompt.user_text,
            "structuring_path": structuring_path,
        }

        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
        return PipeLLMOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    def _format_error_location(self, pipe_run_params: PipeRunParams) -> str:
        return f"in pipe '{pipe_run_params.pipe_stack_str}'"

    def _format_llm_error(self, exc: LLMCompletionError, *, settings: list[LLMSetting]) -> str:
        """Format an LLMCompletionError, extracting and formatting any ValidationError in the chain."""
        error_details = str(exc)
        for current_exc in iter_cause_chain(exc):
            if isinstance(current_exc, ValidationError):
                error_details += f"\n{format_pydantic_validation_error(current_exc)}"
                break
        return f"{error_details}\nLLM settings: {settings}"

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
