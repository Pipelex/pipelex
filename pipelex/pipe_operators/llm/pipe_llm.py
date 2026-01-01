from typing import Literal, cast

from pydantic import ValidationError, model_validator
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.exceptions import LLMCompletionError
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting, LLMSettingChoices
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
from pipelex.pipe_operators.llm.pipe_llm_blueprint import StructuringMethod
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_run_params import (
    PipeRunParamKey,
    PipeRunParams,
    output_multiplicity_to_apply,
)
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error
from pipelex.types import Self


class PipeLLMOutput(PipeOutput):
    pass


class PipeLLM(PipeOperator[PipeLLMOutput]):
    type: Literal["PipeLLM"] = "PipeLLM"
    llm_prompt_spec: LLMPromptBlueprint
    llm_choices: LLMSettingChoices | None = None
    structuring_method: StructuringMethod | None = None
    output_multiplicity: VariableMultiplicity | None = None

    @model_validator(mode="after")
    def validate_output_concept_consistency(self) -> Self:
        if self.structuring_method is not None and self.output.concept.structure_class_name == NativeConceptCode.TEXT:
            msg = (
                f"Output concept '{self.output.concept.code}' is considered a Text concept, "
                f"so it cannot be structured. Maybe you forgot to add '{NativeConceptCode.TEXT}' to the class registry?"
            )
            raise ValueError(msg)
        return self

    @override
    def validate_inputs_static(self):
        if self.llm_choices:
            for llm_choice in self.llm_choices.list_choice_strings():
                check_llm_choice_with_deck(llm_choice=llm_choice)

        needed_inputs = self.needed_inputs()
        required_variable_paths = self.required_variables()
        input_names = {input_name for input_name, _ in needed_inputs.items}

        # Check for unused inputs: declared in inputs but not used by any variable path
        for input_name in input_names:
            if not is_input_used_by_variables(input_name, required_variable_paths):
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
            if not is_variable_satisfied_by_inputs(variable_path, input_names):
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
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        needed_inputs = InputStuffSpecsFactory.make_empty()

        for input_name, stuff_spec in self.inputs.items:
            needed_inputs.add_stuff_spec(variable_name=input_name, concept=stuff_spec.concept, multiplicity=stuff_spec.multiplicity)

        return needed_inputs

    @override
    def required_variables(self) -> set[str]:
        return {variable_name for variable_name in self.llm_prompt_spec.required_variables() if not variable_name.startswith("_")}

    @override
    async def _live_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
    ) -> PipeLLMOutput:
        content_generator = content_generator or get_content_generator()
        # interpret / unwrap the arguments
        output_stuff_spec = self.output
        if self.output.concept.code == SpecialDomain.NATIVE + "." + NativeConceptCode.DYNAMIC:
            # TODO: This DYNAMIC_OUTPUT_CONCEPT should not be a field in the params attribute of PipeRunParams.
            # It should be an attribute of PipeRunParams.
            output_concept_code = pipe_run_params.dynamic_output_concept_code or pipe_run_params.params.get(PipeRunParamKey.DYNAMIC_OUTPUT_CONCEPT)

            if not output_concept_code:
                output_concept_code = SpecialDomain.NATIVE + "." + NativeConceptCode.TEXT
            else:
                output_stuff_spec.concept = get_required_concept(
                    concept_ref=ConceptFactory.make_concept_ref_with_domain(domain_code=self.domain_code, concept_code=output_concept_code),
                )

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
            inference_model := model_deck.get_optional_inference_model(model_handle=llm_setting_main.model)
        ):
            # Note: the case where we don't get an inference model corresponds to the use of an external LLM Plugin
            # TODO: improve this by making it possible to get the inference model for external LLM Plugins
            prompting_target = llm_setting_main.prompting_target or inference_model.prompting_target
            self.llm_prompt_spec.templating_style = get_config().pipelex.prompting_config.get_prompting_style(
                prompting_target=prompting_target,
            )

        is_with_preliminary_text = (
            self.structuring_method == StructuringMethod.PRELIMINARY_TEXT
        ) or get_config().pipelex.structure_config.is_default_text_then_structure
        log.verbose(
            f"is_with_preliminary_text: {is_with_preliminary_text} for pipe {self.code} because the structuring_method is {self.structuring_method}",
        )

        llm_prompt_run_params = PipeRunParams.copy_by_injecting_multiplicity(
            pipe_run_params=pipe_run_params,
            applied_output_multiplicity=applied_output_multiplicity,
            is_with_preliminary_text=is_with_preliminary_text,
        )

        # TODO: we need a better solution for structuring_method (text then object), meanwhile,
        # we acknowledge the code here with llm_prompt_1 and llm_prompt_2 is overly complex and should be refactored.

        the_content: StuffContent

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
            try:
                generated_text: str = await content_generator.make_llm_text(
                    job_metadata=job_metadata,
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
                msg = f"Error generating text content with in PipeLLM {location}: {error_details}"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc
        else:
            if is_multiple_output:
                log.verbose(f"PipeLLM generating {fixed_nb_output} output(s)" if fixed_nb_output else "PipeLLM generating a list of output(s)")
            else:
                log.verbose(f"PipeLLM generating a single object output, class name: '{output_stuff_spec.concept.structure_class_name}'")

            # TODO: we need a better solution for structuring_method (text then object), meanwhile,
            # we acknowledge the code here with llm_prompt_1 and llm_prompt_2 is overly complex and should be refactored.
            llm_prompt_2_factory: LLMPromptFactoryAbstract | None
            if self.structuring_method:
                structuring_method = cast("StructuringMethod", self.structuring_method)
                log.verbose(f"PipeLLM pipe_code is '{self.code}' and structuring_method is '{structuring_method}'")
                match structuring_method:
                    case StructuringMethod.DIRECT:
                        llm_prompt_2_factory = None
                    case StructuringMethod.PRELIMINARY_TEXT:
                        log.verbose(f"Creating llm_prompt_2_factory for pipe {self.code} with structuring_method {structuring_method}")
                        llm_prompt_2_factory = LLMPromptTemplate.make_for_structuring_from_preliminary_text()
            elif get_config().pipelex.structure_config.is_default_text_then_structure:
                log.verbose(f"PipeLLM pipe_code is '{self.code}' and is_default_text_then_structure")
                llm_prompt_2_factory = LLMPromptTemplate.make_for_structuring_from_preliminary_text()
                log.verbose(llm_prompt_2_factory, title="llm_prompt_2_factory")
            else:
                llm_prompt_2_factory = None

            output_structure_prompt: str | None = None
            if get_config().cogt.llm_config.is_structure_prompt_enabled:
                output_structure_prompt = await get_output_structure_prompt(
                    concept_ref=pipe_run_params.dynamic_output_concept_code or output_stuff_spec.concept.concept_ref,
                    is_with_preliminary_text=is_with_preliminary_text,
                )
            llm_prompt_1_for_object = await self.llm_prompt_spec.make_llm_prompt(
                output_concept_ref=output_stuff_spec.concept.concept_ref,
                context_provider=working_memory,
                output_structure_prompt=output_structure_prompt,
                extra_params=llm_prompt_run_params.params,
            )
            the_content = await self._llm_gen_object_stuff_content(
                job_metadata=job_metadata,
                pipe_run_params=pipe_run_params,
                is_multiple_output=is_multiple_output,
                fixed_nb_output=fixed_nb_output,
                output_class_name=output_stuff_spec.concept.structure_class_name,
                llm_setting_main=llm_setting_main,
                llm_setting_for_object=llm_setting_for_object,
                llm_prompt_1=llm_prompt_1_for_object,
                llm_prompt_2_factory=llm_prompt_2_factory,
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

        return PipeLLMOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    async def _llm_gen_object_stuff_content(
        self,
        job_metadata: JobMetadata,
        pipe_run_params: PipeRunParams,
        is_multiple_output: bool,
        fixed_nb_output: int | None,
        output_class_name: str,
        llm_setting_main: LLMSetting,
        llm_setting_for_object: LLMSetting,
        llm_prompt_1: LLMPrompt,
        llm_prompt_2_factory: LLMPromptFactoryAbstract | None,
        content_generator: ContentGeneratorProtocol,
    ) -> StuffContent:
        content_class: type[StuffContent] = get_class_registry().get_required_subclass(name=output_class_name, base_class=StuffContent)
        task_desc: str
        the_content: StuffContent

        if is_multiple_output:
            # We're generating a list of (possibly multiple) objects
            if fixed_nb_output:
                task_desc = f"{self.__class__.__name__}_gen_{fixed_nb_output}x{content_class.__class__.__name__}"
            else:
                task_desc = f"{self.__class__.__name__}_gen_list_{content_class.__class__.__name__}"
            log.verbose(task_desc)
            generated_objects: list[StuffContent]
            if llm_prompt_2_factory is not None:
                # We're generating a list of objects using preliminary text
                method_desc = "text_then_object"
                log.verbose(f"{task_desc} by {method_desc}")
                log.verbose(f"llm_prompt_2_factory: {llm_prompt_2_factory}")
                try:
                    generated_objects = await content_generator.make_text_then_object_list(
                        job_metadata=job_metadata,
                        object_class=content_class,
                        llm_prompt_for_text=llm_prompt_1,
                        llm_setting_main=llm_setting_main,
                        llm_prompt_factory_for_object_list=llm_prompt_2_factory,
                        llm_setting_for_object_list=llm_setting_for_object,
                        nb_items=fixed_nb_output,
                    )
                except LLMCompletionError as exc:
                    location = self._format_error_location(pipe_run_params=pipe_run_params)
                    error_details = self._format_llm_error(exc=exc, settings=[llm_setting_main, llm_setting_for_object])
                    msg = f"Error generating list of objects with text then object {location}: {error_details}"
                    raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc
            else:
                # We're generating a list of objects directly
                method_desc = "object_direct"
                log.verbose(f"{task_desc} by {method_desc}, content_class={content_class.__name__}")
                try:
                    generated_objects = await content_generator.make_object_list_direct(
                        job_metadata=job_metadata,
                        object_class=content_class,
                        llm_prompt_for_object_list=llm_prompt_1,
                        llm_setting_for_object_list=llm_setting_for_object,
                        nb_items=fixed_nb_output,
                    )
                except LLMCompletionError as exc:
                    location = self._format_error_location(pipe_run_params=pipe_run_params)
                    error_details = self._format_llm_error(exc=exc, settings=[llm_setting_for_object])
                    msg = f"Error generating list of objects with direct method {location}: {error_details}"
                    raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

            the_content = ListContent(items=generated_objects)
        else:
            # We're generating a single object
            task_desc = f"{self.__class__.__name__}_gen_single_{content_class.__name__}"
            log.verbose(task_desc)
            if llm_prompt_2_factory is not None:
                # We're generating a single object using preliminary text
                method_desc = "text_then_object"
                log.verbose(f"{task_desc} by {method_desc}")
                log.verbose(f"llm_prompt_2_factory: {llm_prompt_2_factory}")
                try:
                    generated_object = await content_generator.make_text_then_object(
                        job_metadata=job_metadata,
                        object_class=content_class,
                        llm_prompt_for_text=llm_prompt_1,
                        llm_setting_main=llm_setting_main,
                        llm_prompt_factory_for_object=llm_prompt_2_factory,
                        llm_setting_for_object=llm_setting_for_object,
                    )
                except LLMCompletionError as exc:
                    location = self._format_error_location(pipe_run_params=pipe_run_params)
                    error_details = self._format_llm_error(exc=exc, settings=[llm_setting_main, llm_setting_for_object])
                    msg = f"Error generating single object with text then object {location}: {error_details}"
                    raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc
            else:
                # We're generating a single object directly
                method_desc = "object_direct"
                log.verbose(f"{task_desc} by {method_desc}, content_class={content_class.__name__}")
                try:
                    generated_object = await content_generator.make_object_direct(
                        job_metadata=job_metadata,
                        object_class=content_class,
                        llm_prompt_for_object=llm_prompt_1,
                        llm_setting_for_object=llm_setting_for_object,
                    )
                except LLMCompletionError as exc:
                    location = self._format_error_location(pipe_run_params=pipe_run_params)
                    error_details = self._format_llm_error(exc=exc, settings=[llm_setting_for_object])
                    msg = f"Error generating single object with direct method {location}: {error_details}"
                    raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc
            the_content = generated_object

        return the_content

    def _format_error_location(self, pipe_run_params: PipeRunParams) -> str:
        return f"in pipe '{pipe_run_params.pipe_stack_str}'"

    def _format_llm_error(self, exc: LLMCompletionError, settings: list[LLMSetting]) -> str:
        """Format an LLMCompletionError, extracting and formatting any ValidationError in the chain."""
        error_details = str(exc)
        current_exc: BaseException | None = exc
        while current_exc is not None:
            if isinstance(current_exc, ValidationError):
                error_details += f"\n{format_pydantic_validation_error(current_exc)}"
                break
            current_exc = current_exc.__cause__
        return f"{error_details}\nLLM settings: {settings}"

    @override
    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeLLMOutput:
        return await self._live_run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            content_generator=ContentGeneratorDry(),
        )

    @override
    async def _validate_before_run(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    @override
    async def _validate_after_run(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
