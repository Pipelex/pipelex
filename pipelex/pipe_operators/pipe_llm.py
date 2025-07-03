from typing import List, Optional, Set, Type, cast

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.llm.llm_models.llm_deck_check import check_llm_setting_with_deck
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting, LLMSettingChoices, LLMSettingOrPresetId
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.config import StaticValidationReaction, get_config
from pipelex.core.concept_code_factory import ConceptCodeFactory
from pipelex.core.concept_native import NativeConcept, NativeConceptClass
from pipelex.core.domain import Domain, SpecialDomain
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import (
    PipeOutputMultiplicity,
    PipeRunParamKey,
    PipeRunParams,
    output_multiplicity_to_apply,
)
from pipelex.core.stuff_content import ListContent, StructuredContent, StuffContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import (
    PipeDefinitionError,
    PipeInputError,
    PipeInputNotFoundError,
    StaticValidationError,
    StaticValidationErrorType,
)
from pipelex.hub import (
    get_class_registry,
    get_concept_provider,
    get_content_generator,
    get_llm_deck,
    get_optional_pipe,
    get_required_concept,
    get_required_domain,
    get_required_pipe,
    get_template,
)
from pipelex.pipe_operators.pipe_jinja2_factory import PipeJinja2Factory
from pipelex.pipe_operators.pipe_llm_prompt import PipeLLMPrompt, PipeLLMPromptOutput
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_operators.piped_llm_prompt_factory import PipedLLMPromptFactory
from pipelex.pipeline.job_metadata import JobCategory, JobMetadata
from pipelex.types import StrEnum


class StructuringMethod(StrEnum):
    DIRECT = "direct"
    PRELIMINARY_TEXT = "preliminary_text"


class PipeLLMOutput(PipeOutput):
    pass


class PipeLLM(PipeOperator):
    pipe_llm_prompt: PipeLLMPrompt
    llm_choices: Optional[LLMSettingChoices] = None
    structuring_method: Optional[StructuringMethod] = None
    prompt_template_to_structure: Optional[str] = None
    system_prompt_to_structure: Optional[str] = None
    output_multiplicity: Optional[PipeOutputMultiplicity] = None

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        self._validate_required_variables()
        self._validate_inputs()
        return self

    @model_validator(mode="after")
    def validate_output_concept_consistency(self) -> Self:
        if self.structuring_method is not None:
            output_concept = get_required_concept(concept_code=self.output_concept_code)
            if output_concept.structure_class_name == NativeConceptClass.TEXT:
                raise PipeDefinitionError(f"Output concept '{self.output_concept_code}' is a Text concept, so it cannot be structured")
        return self

    @override
    def validate_with_libraries(self):
        self._validate_inputs()
        self.pipe_llm_prompt.validate_with_libraries()
        if self.prompt_template_to_structure:
            get_template(template_name=self.prompt_template_to_structure)
        if self.system_prompt_to_structure:
            get_template(template_name=self.system_prompt_to_structure)
        if self.llm_choices:
            for llm_setting in self.llm_choices.list_used_presets():
                check_llm_setting_with_deck(llm_setting_or_preset_id=llm_setting)

    @override
    def needed_inputs(self) -> PipeInputSpec:
        """Needed inputs are the inputs needed to run the pipe, specified in the inputs attribute of the pipe"""
        # The images are not tagged in the prompt_template.
        # Therefore if an image is provided in the inputs, it becomes a needed input.
        needed_inputs = PipeInputSpec.make_empty()
        concept_provider = get_concept_provider()

        for input_name, concept_code in self.inputs.items:
            if concept_provider.is_image_concept(concept_code=concept_code):
                needed_inputs.add_requirement(variable_name=input_name, concept_code=NativeConcept.IMAGE.code)
            else:
                needed_inputs.add_requirement(variable_name=input_name, concept_code=concept_code)

        return needed_inputs

    @override
    def required_variables(self) -> Set[str]:
        """Required variables are the variables that are used in the current prompt template or system prompt"""
        required_variables: Set[str] = set()
        required_variables.update(self.pipe_llm_prompt.required_variables())
        required_variables = {variable_name for variable_name in required_variables if not variable_name.startswith("_")}
        return required_variables

    def _validate_required_variables(self) -> Self:
        """This method checks that all required variables are in the inputs"""
        required_variables = self.required_variables()
        for required_variable_name in required_variables:
            if required_variable_name not in self.inputs.variables:
                raise PipeDefinitionError(f"Required variable '{required_variable_name}' is not in the inputs of pipe {self.code}")
        return self

    def _validate_inputs(self):
        concept_provider = get_concept_provider()
        static_validation_config = get_config().pipelex.static_validation_config
        default_reaction = static_validation_config.default_reaction
        reactions = static_validation_config.reactions

        the_needed_inputs = self.needed_inputs()
        # check all required variables are in the inputs
        for required_variable_name, requirement_expression, concept_code in the_needed_inputs.detailed_requirements:
            if required_variable_name not in self.inputs.variables:
                missing_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain_code=self.domain,
                    pipe_code=self.code,
                    variable_names=[required_variable_name],
                )
                match reactions.get(StaticValidationErrorType.MISSING_INPUT_VARIABLE, default_reaction):
                    case StaticValidationReaction.IGNORE:
                        pass
                    case StaticValidationReaction.LOG:
                        log.error(missing_input_var_error.desc())
                    case StaticValidationReaction.RAISE:
                        raise missing_input_var_error

            # there is one case where the needed input is of specific concept: the user_images
            if concept_code == NativeConcept.IMAGE.code:
                try:
                    concept_code_of_declared_input = self.inputs.get_required_concept_code(variable_name=required_variable_name)
                except PipeInputNotFoundError as exc:
                    raise PipeInputError(
                        f"Input variable '{required_variable_name}' is not in this PipeLLM '{self.code}' input spec: {self.inputs}"
                    ) from exc
                if not concept_provider.is_compatible_by_concept_code(
                    tested_concept_code=concept_code_of_declared_input,
                    wanted_concept_code=concept_code,
                ):
                    if required_variable_name != requirement_expression:
                        # the required_input is a sub-attribute of the required variable
                        # TODO: check that the sub-attribute is compatible with the concept code
                        # let's check at least that the input is a structured concept
                        input_concept = concept_provider.get_required_concept(concept_code=concept_code_of_declared_input)
                        input_concept_class_name = input_concept.structure_class_name
                        input_concept_class = get_class_registry().get_required_subclass(name=input_concept_class_name, base_class=StuffContent)
                        if issubclass(input_concept_class, StructuredContent):
                            continue
                    explanation = "The input provided for LLM Vision must be an image or a concept that refines image"
                    if inadequate_concept := get_concept_provider().get_concept(concept_code=concept_code_of_declared_input):
                        explanation += f",\nconcept = {inadequate_concept}"
                    else:
                        explanation += ",\nconcept not found"

                    inadequate_input_concept_error = StaticValidationError(
                        error_type=StaticValidationErrorType.INADEQUATE_INPUT_CONCEPT,
                        domain_code=self.domain,
                        pipe_code=self.code,
                        variable_names=[required_variable_name],
                        provided_concept_code=concept_code_of_declared_input,
                        explanation=explanation,
                    )
                    match reactions.get(StaticValidationErrorType.INADEQUATE_INPUT_CONCEPT, default_reaction):
                        case StaticValidationReaction.IGNORE:
                            pass
                        case StaticValidationReaction.LOG:
                            log.error(inadequate_input_concept_error.desc())
                        case StaticValidationReaction.RAISE:
                            raise inadequate_input_concept_error
        # check that all inputs are in the required variables
        for input_name in self.inputs.variables:
            if input_name not in the_needed_inputs.required_names:
                extraneous_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    domain_code=self.domain,
                    pipe_code=self.code,
                    variable_names=[input_name],
                )
                match reactions.get(StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE, default_reaction):
                    case StaticValidationReaction.IGNORE:
                        pass
                    case StaticValidationReaction.LOG:
                        log.error(extraneous_input_var_error.desc())
                    case StaticValidationReaction.RAISE:
                        raise extraneous_input_var_error
            else:
                # Check if this input is an image concept but is being used as a variable in the prompt
                if concept_provider.is_image_concept(concept_code=input_name):
                    raise PipeDefinitionError(
                        f"Image-based input '{input_name}' of concept '{input_name}' "
                        f"cannot be used as a variable in a prompt for Pipe '{self.code}'. "
                        f"Image variables are automatically passed to vision-enabled LLMs."
                    )

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
        content_generator: Optional[ContentGeneratorProtocol] = None,
    ) -> PipeLLMOutput:
        content_generator = content_generator or get_content_generator()
        # interpret / unwrap the arguments
        log.debug(f"PipeLLM pipe_code = {self.code}")
        if self.output_concept_code == ConceptCodeFactory.make_concept_code(
            SpecialDomain.NATIVE,
            NativeConcept.DYNAMIC.code,
        ):
            # TODO: This DYNAMIC_OUTPUT_CONCEPT should not be a field in the params attribute of PipeRunParams.
            # It should be an attribute of PipeRunParams.
            output_concept_code = pipe_run_params.dynamic_output_concept_code or pipe_run_params.params.get(PipeRunParamKey.DYNAMIC_OUTPUT_CONCEPT)

            if not output_concept_code:
                output_concept_code = NativeConcept.TEXT.code
        else:
            output_concept_code = self.output_concept_code

        self.pipe_llm_prompt.output_concept_code = output_concept_code

        applied_output_multiplicity, is_multiple_output, fixed_nb_output = output_multiplicity_to_apply(
            output_multiplicity_base=self.output_multiplicity,
            output_multiplicity_override=pipe_run_params.output_multiplicity,
        )
        log.debug(
            f"PipeLLM pipe_code = {self.code}: applied_output_multiplicity = {applied_output_multiplicity}, "
            f"is_multiple_output = {is_multiple_output}, fixed_nb_output = {fixed_nb_output}"
        )

        output_concept = get_required_concept(concept_code=output_concept_code)
        if is_multiple_output:
            if fixed_nb_output:
                log.verbose(f"{self.class_name} generate {fixed_nb_output} x '{output_concept_code}' (class '{output_concept.structure_class_name}')")
            else:
                log.verbose(f"{self.class_name} generate a list of '{output_concept_code}' (class '{output_concept.structure_class_name}')")
        else:
            log.verbose(f"{self.class_name} generate a single '{output_concept_code}' (class '{output_concept.structure_class_name}')")

        # Collect what LLM settings we have for this particular PipeLLM
        llm_for_text_choice: Optional[LLMSettingOrPresetId] = None
        llm_for_object_choice: Optional[LLMSettingOrPresetId] = None
        if self.llm_choices:
            llm_for_text_choice = self.llm_choices.for_text
            llm_for_object_choice = self.llm_choices.for_object

        # Choice of main LLM for text first from this PipeLLM setting (self.llm_choices)
        # or from the llm_choice_overrides or fallback on the llm_choice_defaults
        llm_setting_or_preset_id_for_text: LLMSettingOrPresetId = (
            llm_for_text_choice or get_llm_deck().llm_choice_overrides.for_text or get_llm_deck().llm_choice_defaults.for_text
        )
        llm_setting_main: LLMSetting = get_llm_deck().get_llm_setting(llm_setting_or_preset_id=llm_setting_or_preset_id_for_text)

        # Choice of main LLM for object from this PipeLLM setting (self.llm_choices)
        # OR FROM THE llm_for_text_choice (if any)
        # then fallback on the llm_choice_overrides or llm_choice_defaults
        llm_setting_or_preset_id_for_object: LLMSettingOrPresetId = (
            llm_for_object_choice
            or llm_for_text_choice
            or get_llm_deck().llm_choice_overrides.for_object
            or get_llm_deck().llm_choice_defaults.for_object
        )
        llm_setting_for_object: LLMSetting = get_llm_deck().get_llm_setting(llm_setting_or_preset_id=llm_setting_or_preset_id_for_object)

        if not self.pipe_llm_prompt.prompting_style and (llm_model := get_llm_deck().find_optional_llm_model(llm_handle=llm_setting_main.llm_handle)):
            llm_family = llm_model.llm_family
            if llm_setting_main.prompting_target:
                log.dev(f"prompting_target for '{llm_setting_main.llm_handle}' from setting: {llm_setting_main}")
            else:
                log.dev(f"prompting_target for '{llm_setting_main.llm_handle}' from llm_family: {llm_family}")
            prompting_target = llm_setting_main.prompting_target or llm_family.prompting_target
            self.pipe_llm_prompt.prompting_style = get_config().pipelex.prompting_config.get_prompting_style(
                prompting_target=prompting_target,
            )

        # prepare the job
        prompt_job_metadata = job_metadata.copy_with_update(
            updated_metadata=JobMetadata(
                job_category=JobCategory.PROMPTING_JOB,
            )
        )

        llm_prompt_run_params = PipeRunParams.copy_by_injecting_multiplicity(
            pipe_run_params=pipe_run_params,
            applied_output_multiplicity=applied_output_multiplicity,
        )
        # llm_prompt_1: LLMPrompt = (
        #     await self.pipe_llm_prompt.run_pipe(
        #         job_metadata=prompt_job_metadata,
        #         working_memory=working_memory,
        #         pipe_run_params=llm_prompt_run_params,
        #     )
        # ).llm_prompt
        # TODO: restore the possibility above, without need to explicitly cast the output
        pipe_output: PipeOutput = await self.pipe_llm_prompt.run_pipe(
            job_metadata=prompt_job_metadata,
            working_memory=working_memory,
            pipe_run_params=llm_prompt_run_params,
        )
        llm_prompt_1 = cast(PipeLLMPromptOutput, pipe_output).llm_prompt

        the_content: StuffContent
        if output_concept.structure_class_name == NativeConceptClass.TEXT and not is_multiple_output:
            log.debug(f"PipeLLM generating a single text output: {self.class_name}_gen_text")
            generated_text: str = await content_generator.make_llm_text(
                job_metadata=job_metadata,
                llm_prompt_for_text=llm_prompt_1,
                llm_setting_main=llm_setting_main,
            )

            the_content = TextContent(
                text=generated_text,
            )
        else:
            log.debug(f"PipeLLM generating {fixed_nb_output} output(s)" if fixed_nb_output else "PipeLLM generating a list of output(s)")

            llm_prompt_2_factory: Optional[LLMPromptFactoryAbstract]
            if structuring_method := self.structuring_method:
                log.debug(f"PipeLLM pipe_code is '{self.code}' and structuring_method is '{structuring_method}'")
                match structuring_method:
                    case StructuringMethod.DIRECT:
                        llm_prompt_2_factory = None
                    case StructuringMethod.PRELIMINARY_TEXT:
                        pipe = get_required_pipe(pipe_code=self.code)
                        # TODO: run_pipe() could get the domain at the same time as the pip_code
                        domain = get_required_domain(domain_code=pipe.domain)
                        prompt_template_to_structure = self.prompt_template_to_structure or domain.prompt_template_to_structure
                        user_pipe_jinja2 = PipeJinja2Factory.make_pipe_jinja2_to_structure(
                            domain_code=self.domain,
                            prompt_template_to_structure=prompt_template_to_structure,
                        )
                        system_prompt = self.system_prompt_to_structure or domain.system_prompt
                        pipe_llm_prompt_2 = PipeLLMPrompt(
                            code="adhoc_for_pipe_llm_prompt_2",
                            domain=self.domain,
                            user_pipe_jinja2=user_pipe_jinja2,
                            system_prompt=system_prompt,
                            output_concept_code=output_concept_code,
                        )
                        llm_prompt_2_factory = PipedLLMPromptFactory(
                            pipe_llm_prompt=pipe_llm_prompt_2,
                        )
            elif get_config().pipelex.structure_config.is_default_text_then_structure:
                log.debug(f"PipeLLM pipe_code is '{self.code}' and is_default_text_then_structure")
                # TODO: run_pipe() should get the domain along with the pip_code
                if the_pipe := get_optional_pipe(pipe_code=self.code):
                    domain = get_required_domain(domain_code=the_pipe.domain)
                else:
                    domain = Domain.make_default()
                prompt_template_to_structure = self.prompt_template_to_structure or domain.prompt_template_to_structure
                user_pipe_jinja2 = PipeJinja2Factory.make_pipe_jinja2_to_structure(
                    domain_code=self.domain,
                    prompt_template_to_structure=prompt_template_to_structure,
                )
                system_prompt = self.system_prompt_to_structure or domain.system_prompt
                pipe_llm_prompt_2 = PipeLLMPrompt(
                    code="adhoc_for_pipe_llm_prompt_2",
                    domain=self.domain,
                    user_pipe_jinja2=user_pipe_jinja2,
                    system_prompt=system_prompt,
                    output_concept_code=output_concept_code,
                )
                llm_prompt_2_factory = PipedLLMPromptFactory(
                    pipe_llm_prompt=pipe_llm_prompt_2,
                )
            else:
                llm_prompt_2_factory = None

            the_content = await self._llm_gen_object_stuff_content(
                job_metadata=job_metadata,
                is_multiple_output=is_multiple_output,
                fixed_nb_output=fixed_nb_output,
                output_class_name=output_concept.structure_class_name,
                llm_setting_main=llm_setting_main,
                llm_setting_for_object=llm_setting_for_object,
                llm_prompt_1=llm_prompt_1,
                llm_prompt_2_factory=llm_prompt_2_factory,
                content_generator=content_generator,
            )

        output_stuff = StuffFactory.make_stuff_using_concept(
            name=output_name,
            concept=output_concept,
            content=the_content,
            code=pipe_run_params.final_stuff_code,
        )
        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        pipe_output = PipeLLMOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )
        return pipe_output

    async def _llm_gen_object_stuff_content(
        self,
        job_metadata: JobMetadata,
        is_multiple_output: bool,
        fixed_nb_output: Optional[int],
        output_class_name: str,
        llm_setting_main: LLMSetting,
        llm_setting_for_object: LLMSetting,
        llm_prompt_1: LLMPrompt,
        llm_prompt_2_factory: Optional[LLMPromptFactoryAbstract],
        content_generator: ContentGeneratorProtocol,
    ) -> StuffContent:
        content_class: Type[StuffContent] = get_class_registry().get_required_subclass(name=output_class_name, base_class=StuffContent)
        task_desc: str
        the_content: StuffContent

        if is_multiple_output:
            # We're generating a list of (possibly multiple) objects
            if fixed_nb_output:
                task_desc = f"{self.class_name}_gen_{fixed_nb_output}x{content_class.__class__.__name__}"
            else:
                task_desc = f"{self.class_name}_gen_list_{content_class.__class__.__name__}"
            log.dev(task_desc)
            generated_objects: List[StuffContent]
            if llm_prompt_2_factory is not None:
                # We're generating a list of objects using preliminary text
                method_desc = "text_then_object"
                log.dev(f"{task_desc} by {method_desc}")

                generated_objects = await content_generator.make_text_then_object_list(
                    job_metadata=job_metadata,
                    object_class=content_class,
                    llm_prompt_for_text=llm_prompt_1,
                    llm_setting_main=llm_setting_main,
                    llm_prompt_factory_for_object_list=llm_prompt_2_factory,
                    llm_setting_for_object_list=llm_setting_for_object,
                    nb_items=fixed_nb_output,
                )
            else:
                # We're generating a list of objects directly
                method_desc = "object_direct"
                log.dev(f"{task_desc} by {method_desc}, content_class={content_class.__name__}")
                generated_objects = await content_generator.make_object_list_direct(
                    job_metadata=job_metadata,
                    object_class=content_class,
                    llm_prompt_for_object_list=llm_prompt_1,
                    llm_setting_for_object_list=llm_setting_for_object,
                    nb_items=fixed_nb_output,
                )

            the_content = ListContent(items=generated_objects)
        else:
            # We're generating a single object
            task_desc = f"{self.class_name}_gen_single_{content_class.__name__}"
            log.verbose(task_desc)
            if llm_prompt_2_factory is not None:
                # We're generating a single object using preliminary text
                method_desc = "text_then_object"
                log.verbose(f"{task_desc} by {method_desc}")
                generated_object = await content_generator.make_text_then_object(
                    job_metadata=job_metadata,
                    object_class=content_class,
                    llm_prompt_for_text=llm_prompt_1,
                    llm_setting_main=llm_setting_main,
                    llm_prompt_factory_for_object=llm_prompt_2_factory,
                    llm_setting_for_object=llm_setting_for_object,
                )
            else:
                # We're generating a single object directly
                method_desc = "object_direct"
                log.verbose(f"{task_desc} by {method_desc}, content_class={content_class.__name__}")
                generated_object = await content_generator.make_object_direct(
                    job_metadata=job_metadata,
                    object_class=content_class,
                    llm_prompt_for_object=llm_prompt_1,
                    llm_setting_for_object=llm_setting_for_object,
                )
            the_content = generated_object

        return the_content

    @override
    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        content_generator_dry = ContentGeneratorDry()
        pipe_output = await self._run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            content_generator=content_generator_dry,
        )
        return pipe_output
