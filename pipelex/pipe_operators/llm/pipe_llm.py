from typing import Any, Literal

from pydantic import ValidationError
from typing_extensions import override

from pipelex import log
from pipelex.base_exceptions import iter_cause_chain
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.exceptions import LLMCompletionError
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting, LLMSettingChoices
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck_check import check_llm_choice_with_deck
from pipelex.config import get_config
from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.domains.domain import SpecialDomain
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.validation import is_input_used_by_variables, is_variable_satisfied_by_inputs
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import (
    get_class_registry,
    get_concept_library,
    get_content_generator,
    get_model_deck,
    get_native_concept,
    get_required_concept,
)
from pipelex.pipe_operators.llm.helpers import get_output_structure_prompt
from pipelex.pipe_operators.llm.llm_prompt_blueprint import LLMPromptBlueprint
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_run_params import (
    PipeRunParamKey,
    PipeRunParams,
    output_multiplicity_to_apply,
)
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error


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
                    pipe_code=self.code,
                    variable_names=[variable_path],
                    explanation=f"Variable '{variable_path}' is used in prompt/system_prompt but not declared in inputs.",
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
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
            )

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        needed_inputs = InputStuffSpecsFactory.make_empty()

        for input_name, stuff_spec in self.inputs.items:
            needed_inputs.add_stuff_spec(variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity)

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
        content_generator = get_content_generator()
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

        model_deck = get_model_deck()

        # Choice of main LLM for text first from this PipeLLM setting (self.llm_choices)
        # or from the llm_choice_overrides or fallback on the llm_choice_defaults
        llm_setting_or_preset_id_for_text: LLMModelChoice = (
            llm_for_text_choice or model_deck.llm_choice_overrides.for_text or model_deck.llm_choice_defaults.for_text
        )
        llm_setting_main: LLMSetting = model_deck.get_llm_setting(llm_choice=llm_setting_or_preset_id_for_text)

        # Choice of main LLM for object from this PipeLLM setting (self.llm_choices)
        # OR FROM THE llm_for_text_choice (if any)
        # then fallback on the llm_choice_overrides or llm_choice_defaults
        llm_setting_or_preset_id_for_object: LLMModelChoice = (
            llm_for_object_choice or llm_for_text_choice or model_deck.llm_choice_overrides.for_object or model_deck.llm_choice_defaults.for_object
        )
        llm_setting_for_object: LLMSetting = model_deck.get_llm_setting(llm_choice=llm_setting_or_preset_id_for_object)

        if (not self.llm_prompt_spec.templating_style) and (
            inference_model := model_deck.get_optional_inference_model(model_handle=llm_setting_main.model, model_type=ModelType.LLM)
        ):
            # Note: the case where we don't get an inference model corresponds to the use of an external LLM plugin
            # TODO: improve this by making it possible to get the inference model for external LLM plugins
            prompting_target = llm_setting_main.prompting_target or inference_model.prompting_target
            self.llm_prompt_spec.templating_style = get_config().pipelex.prompting_config.get_prompting_style(
                prompting_target=prompting_target,
            )

        llm_prompt_run_params = PipeRunParams.copy_by_injecting_multiplicity(
            pipe_run_params=pipe_run_params,
            applied_output_multiplicity=applied_output_multiplicity,
        )

        the_content: StuffContent
        rendered_llm_prompt: LLMPrompt | None = None

        if (
            Concept.are_concept_compatible(concept_1=output_stuff_spec.concept, concept_2=get_native_concept(NativeConceptCode.TEXT), strict=True)
            and not is_multiple_output
        ):
            llm_prompt_1_for_text = await self.llm_prompt_spec.make_llm_prompt(
                output_concept_ref=output_stuff_spec.concept.concept_ref,
                context_provider=working_memory,
                output_structure_prompt=None,
                extra_params=llm_prompt_run_params.params,
            )
            rendered_llm_prompt = llm_prompt_1_for_text
            try:
                generated_text: str = await content_generator.make_llm_text(
                    job_metadata=job_metadata,
                    cogt_run_params=pipe_run_params.cogt_run_params,
                    llm_prompt_for_text=llm_prompt_1_for_text,
                    llm_setting_main=llm_setting_main,
                )
            except LLMCompletionError as exc:
                location = self._format_error_location(pipe_run_params=pipe_run_params)
                error_details = self._format_llm_error(exc=exc, settings=[llm_setting_main])
                msg = f"Error generating text with LLM {location}: {error_details}"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

            structure_class = get_class_registry().get_required_subclass(
                name=output_stuff_spec.concept.structure_class_name,
                base_class=StuffContent,
            )

            try:
                the_content = structure_class(
                    text=generated_text,
                )
            except ValidationError as exc:
                location = self._format_error_location(pipe_run_params=pipe_run_params)
                error_details = format_pydantic_validation_error(exc)
                msg = f"Error generating text content in PipeLLM {location}: {error_details}"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc
        else:
            if is_multiple_output:
                log.verbose(f"PipeLLM generating {fixed_nb_output} output(s)" if fixed_nb_output else "PipeLLM generating a list of output(s)")
            else:
                log.verbose(f"PipeLLM generating a single object output, class name: '{output_stuff_spec.concept.structure_class_name}'")

            output_structure_prompt: str | None = None
            if get_config().cogt.llm_config.is_structure_prompt_enabled:
                output_structure_prompt = await get_output_structure_prompt(
                    concept_ref=output_stuff_spec.concept.concept_ref,
                )
            llm_prompt_for_object = await self.llm_prompt_spec.make_llm_prompt(
                output_concept_ref=output_stuff_spec.concept.concept_ref,
                context_provider=working_memory,
                output_structure_prompt=output_structure_prompt,
                extra_params=llm_prompt_run_params.params,
            )
            rendered_llm_prompt = llm_prompt_for_object
            the_content = await self._llm_gen_object_stuff_content(
                job_metadata=job_metadata,
                pipe_run_params=pipe_run_params,
                is_multiple_output=is_multiple_output,
                fixed_nb_output=fixed_nb_output,
                output_class_name=output_stuff_spec.concept.structure_class_name,
                llm_setting_for_object=llm_setting_for_object,
                llm_prompt_for_object=llm_prompt_for_object,
                content_generator=content_generator,
            )

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=output_stuff_spec.concept,
            content=the_content,
            code=pipe_run_params.final_stuff_code,
        )
        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        # Capture execution data for the graph tracer
        execution_data_dict: dict[str, Any] = {
            "resolved_model": llm_setting_main.model,
            "resolved_model_for_object": llm_setting_for_object.model,
            "is_multiple_output": is_multiple_output,
        }
        execution_data_dict["rendered_system_prompt"] = rendered_llm_prompt.system_text
        execution_data_dict["rendered_user_prompt"] = rendered_llm_prompt.user_text
        if is_multiple_output:
            execution_data_dict["structuring_path"] = "object_list"
        else:
            output_is_text = Concept.are_concept_compatible(
                concept_1=output_stuff_spec.concept, concept_2=get_native_concept(NativeConceptCode.TEXT), strict=True
            )
            execution_data_dict["structuring_path"] = "text" if output_is_text else "object_direct"

        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
        return PipeLLMOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    async def _llm_gen_object_stuff_content(
        self,
        *,
        job_metadata: JobMetadata,
        pipe_run_params: PipeRunParams,
        is_multiple_output: bool,
        fixed_nb_output: int | None,
        output_class_name: str,
        llm_setting_for_object: LLMSetting,
        llm_prompt_for_object: LLMPrompt,
        content_generator: ContentGeneratorProtocol,
    ) -> StuffContent:
        content_class: type[StuffContent] = get_class_registry().get_required_subclass(name=output_class_name, base_class=StuffContent)

        if is_multiple_output:
            if fixed_nb_output:
                task_desc = f"{self.__class__.__name__}_gen_{fixed_nb_output}x{content_class.__name__}"
            else:
                task_desc = f"{self.__class__.__name__}_gen_list_{content_class.__name__}"
            log.verbose(f"{task_desc} by object_direct")
            try:
                generated_objects = await content_generator.make_object_list(
                    job_metadata=job_metadata,
                    cogt_run_params=pipe_run_params.cogt_run_params,
                    object_class=content_class,
                    llm_prompt_for_object_list=llm_prompt_for_object,
                    llm_setting_for_object_list=llm_setting_for_object,
                    nb_items=fixed_nb_output,
                )
            except LLMCompletionError as exc:
                location = self._format_error_location(pipe_run_params=pipe_run_params)
                error_details = self._format_llm_error(exc=exc, settings=[llm_setting_for_object])
                msg = f"Error generating list of objects with direct method {location}: {error_details}"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

            return ListContent(items=generated_objects)

        task_desc = f"{self.__class__.__name__}_gen_single_{content_class.__name__}"
        log.verbose(f"{task_desc} by object_direct")
        try:
            return await content_generator.make_object(
                job_metadata=job_metadata,
                cogt_run_params=pipe_run_params.cogt_run_params,
                object_class=content_class,
                llm_prompt_for_object=llm_prompt_for_object,
                llm_setting_for_object=llm_setting_for_object,
            )
        except LLMCompletionError as exc:
            location = self._format_error_location(pipe_run_params=pipe_run_params)
            error_details = self._format_llm_error(exc=exc, settings=[llm_setting_for_object])
            msg = f"Error generating single object with direct method {location}: {error_details}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

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
