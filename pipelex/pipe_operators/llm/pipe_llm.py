from typing import Literal, cast

from pydantic import model_validator
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from pipelex.cogt.llm.llm_setting import LLMModelChoice, LLMSetting, LLMSettingChoices
from pipelex.cogt.models.model_deck_check import check_llm_choice_with_deck
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.config import StaticValidationReaction, get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.domains.domain import Domain, SpecialDomain
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.exceptions import (
    PipeDefinitionError,
    StaticValidationError,
    StaticValidationErrorType,
)
from pipelex.hub import (
    get_class_registry,
    get_concept_library,
    get_content_generator,
    get_model_deck,
    get_native_concept,
    get_optional_pipe,
    get_required_concept,
    get_required_domain,
    get_required_pipe,
)
from pipelex.pipe_operators.llm.llm_prompt_blueprint import LLMPromptBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import StructuringMethod
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import (
    PipeOutputMultiplicity,
    PipeRunParamKey,
    PipeRunParams,
    output_multiplicity_to_apply,
)
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.typing.structure_printer import StructurePrinter
from pipelex.types import Self


class PipeLLMOutput(PipeOutput):
    pass


class PipeLLM(PipeOperator[PipeLLMOutput]):
    type: Literal["PipeLLM"] = "PipeLLM"
    llm_prompt_spec: LLMPromptBlueprint
    llm_choices: LLMSettingChoices | None = None
    structuring_method: StructuringMethod | None = None
    prompt_template_to_structure: str | None = None
    system_prompt_to_structure: str | None = None
    output_multiplicity: PipeOutputMultiplicity | None = None

    @model_validator(mode="after")
    def _validate_inputs(self) -> Self:
        self.validate_inputs()
        return self

    @model_validator(mode="after")
    def validate_output_concept_consistency(self) -> Self:
        if self.structuring_method is not None and self.output.structure_class_name == NativeConceptCode.TEXT:
            msg = (
                f"Output concept '{self.output.code}' is considered a Text concept, "
                f"so it cannot be structured. Maybe you forgot to add '{NativeConceptCode.TEXT}' to the class registry?"
            )
            raise PipeDefinitionError(msg)
        return self

    @override
    def validate_with_libraries(self):
        llm_config = get_config().cogt.llm_config
        self.validate_inputs()
        self.llm_prompt_spec.validate_with_libraries()
        if self.prompt_template_to_structure:
            llm_config.get_template(template_name=self.prompt_template_to_structure)
        if self.system_prompt_to_structure:
            llm_config.get_template(template_name=self.system_prompt_to_structure)
        if self.llm_choices:
            for llm_choice in self.llm_choices.list_choices():
                check_llm_choice_with_deck(llm_choice=llm_choice)

    @override
    def validate_output(self):
        if get_concept_library().is_compatible(
            tested_concept=self.output,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.IMAGE),
        ):
            msg = (
                f"The output of a LLM pipe cannot be compatible with the Image concept. In the "
                f"pipe '{self.code}' the output is '{self.output.concept_string}'"
            )
            raise PipeDefinitionError(msg)

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputRequirements:
        """Needed inputs are the inputs needed to run the pipe, specified in the inputs attribute of the pipe"""
        needed_inputs = InputRequirementsFactory.make_empty()

        for input_name, requirement in self.inputs.items:
            needed_inputs.add_requirement(variable_name=input_name, concept=requirement.concept)
        return needed_inputs

    @override
    def required_variables(self) -> set[str]:
        """Required variables are the variables that are used in the current prompt template or system prompt"""
        return {variable_name for variable_name in self.llm_prompt_spec.required_variables() if not variable_name.startswith("_")}

    def validate_inputs(self):
        static_validation_config = get_config().pipelex.static_validation_config
        default_reaction = static_validation_config.default_reaction
        reactions = static_validation_config.reactions
        # Those are the variables required in the prompt template or system prompt
        required_variables = self.required_variables()

        # 1: Check that all the required variables are actually in the inputs
        for required_variable_name in required_variables:
            if required_variable_name not in self.needed_inputs().variables:
                missing_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain=self.domain,
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

        # 2: Check that all inputs are in the required variables
        for input_name, requirement in self.needed_inputs().items:
            if input_name not in required_variables:
                explanation: str | None = None
                if get_concept_library().is_image_concept(concept=requirement.concept):
                    # We have an exraneous image input, the user probably forgot to add it into the prompt template
                    explanation = (
                        f"You have provided an image input named '{input_name}', but it is not referenced in the prompt template. "
                        "Please add it to the prompt template."
                    )

                extraneous_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    domain=self.domain,
                    pipe_code=self.code,
                    variable_names=[input_name],
                    explanation=explanation,
                )
                match reactions.get(StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE, default_reaction):
                    case StaticValidationReaction.IGNORE:
                        pass
                    case StaticValidationReaction.LOG:
                        log.error(extraneous_input_var_error.desc())
                    case StaticValidationReaction.RAISE:
                        raise extraneous_input_var_error

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
    ) -> PipeLLMOutput:
        llm_config = get_config().cogt.llm_config
        content_generator = content_generator or get_content_generator()
        # interpret / unwrap the arguments
        log.debug(f"PipeLLM pipe_code = {self.code}")
        output_concept = self.output
        if self.output.code == SpecialDomain.NATIVE + "." + NativeConceptCode.DYNAMIC:
            # TODO: This DYNAMIC_OUTPUT_CONCEPT should not be a field in the params attribute of PipeRunParams.
            # It should be an attribute of PipeRunParams.
            output_concept_code = pipe_run_params.dynamic_output_concept_code or pipe_run_params.params.get(PipeRunParamKey.DYNAMIC_OUTPUT_CONCEPT)

            if not output_concept_code:
                output_concept_code = SpecialDomain.NATIVE + "." + NativeConceptCode.TEXT
            else:
                output_concept = get_required_concept(
                    concept_string=ConceptFactory.make_concept_string_with_domain(domain=self.domain, concept_code=output_concept_code),
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
        if output_concept.structure_class_name == "TextContent" and not is_multiple_output:
            llm_prompt_1_for_text = await self.llm_prompt_spec.make_llm_prompt(
                output_concept_string=output_concept.concept_string,
                context_provider=working_memory,
                output_structure_prompt=None,
                extra_params=llm_prompt_run_params.params,
            )
            generated_text: str = await content_generator.make_llm_text(
                job_metadata=job_metadata,
                llm_prompt_for_text=llm_prompt_1_for_text,
                llm_setting_main=llm_setting_main,
            )

            the_content = TextContent(
                text=generated_text,
            )
        else:
            if is_multiple_output:
                log.debug(f"PipeLLM generating {fixed_nb_output} output(s)" if fixed_nb_output else "PipeLLM generating a list of output(s)")
            else:
                log.debug(f"PipeLLM generating a single object output, class name: '{output_concept.structure_class_name}'")

            # TODO: we need a better solution for structuring_method (text then object), meanwhile,
            # we acknowledge the code here with llm_prompt_1 and llm_prompt_2 is overly complex and should be refactored.
            llm_prompt_2_factory: LLMPromptFactoryAbstract | None
            if self.structuring_method:
                structuring_method = cast("StructuringMethod", self.structuring_method)
                log.debug(f"PipeLLM pipe_code is '{self.code}' and structuring_method is '{structuring_method}'")
                match structuring_method:
                    case StructuringMethod.DIRECT:
                        llm_prompt_2_factory = None
                    case StructuringMethod.PRELIMINARY_TEXT:
                        log.verbose(f"Creating llm_prompt_2_factory for pipe {self.code} with structuring_method {structuring_method}")
                        pipe = get_required_pipe(pipe_code=self.code)
                        # TODO: run_pipe() could get the domain at the same time as the pip_code
                        domain = get_required_domain(domain=pipe.domain)
                        prompt_template_to_structure = (
                            self.prompt_template_to_structure
                            or domain.prompt_template_to_structure
                            or llm_config.get_template(template_name="structure_from_preliminary_text_user")
                        )
                        system_prompt = self.system_prompt_to_structure or domain.system_prompt
                        llm_prompt_2_proto = LLMPrompt(
                            system_text=system_prompt,
                            user_text=prompt_template_to_structure,
                        )
                        llm_prompt_2_factory = LLMPromptTemplate(
                            proto_prompt=llm_prompt_2_proto,
                        )
            elif get_config().pipelex.structure_config.is_default_text_then_structure:
                log.debug(f"PipeLLM pipe_code is '{self.code}' and is_default_text_then_structure")
                # TODO: run_pipe() should get the domain along with the pip_code
                if the_pipe := get_optional_pipe(pipe_code=self.code):
                    domain = get_required_domain(domain=the_pipe.domain)
                else:
                    domain = Domain.make_default()
                prompt_template_to_structure = (
                    self.prompt_template_to_structure
                    or domain.prompt_template_to_structure
                    or llm_config.get_template(template_name="structure_from_preliminary_text_user")
                )
                system_prompt = self.system_prompt_to_structure or domain.system_prompt
                llm_prompt_2_proto = LLMPrompt(
                    system_text=system_prompt,
                    user_text=prompt_template_to_structure,
                )
                llm_prompt_2_factory = LLMPromptTemplate(
                    proto_prompt=llm_prompt_2_proto,
                )
                log.debug(llm_prompt_2_factory, title="llm_prompt_2_factory")
            else:
                llm_prompt_2_factory = None

            output_structure_prompt: str | None = None
            if llm_config.is_structure_prompt_enabled:
                output_structure_prompt = await PipeLLM.get_output_structure_prompt(
                    concept_string=pipe_run_params.dynamic_output_concept_code or output_concept.concept_string,
                    is_with_preliminary_text=is_with_preliminary_text,
                )
            llm_prompt_1_for_object = await self.llm_prompt_spec.make_llm_prompt(
                output_concept_string=output_concept.concept_string,
                context_provider=working_memory,
                output_structure_prompt=output_structure_prompt,
                extra_params=llm_prompt_run_params.params,
            )
            the_content = await self._llm_gen_object_stuff_content(
                job_metadata=job_metadata,
                is_multiple_output=is_multiple_output,
                fixed_nb_output=fixed_nb_output,
                output_class_name=output_concept.structure_class_name,
                llm_setting_main=llm_setting_main,
                llm_setting_for_object=llm_setting_for_object,
                llm_prompt_1=llm_prompt_1_for_object,
                llm_prompt_2_factory=llm_prompt_2_factory,
                content_generator=content_generator,
            )

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=output_concept,
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
            log.dev(task_desc)
            generated_objects: list[StuffContent]
            if llm_prompt_2_factory is not None:
                # We're generating a list of objects using preliminary text
                method_desc = "text_then_object"
                log.dev(f"{task_desc} by {method_desc}")
                log.verbose(f"llm_prompt_2_factory: {llm_prompt_2_factory}")

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
            task_desc = f"{self.__class__.__name__}_gen_single_{content_class.__name__}"
            log.verbose(task_desc)
            if llm_prompt_2_factory is not None:
                # We're generating a single object using preliminary text
                method_desc = "text_then_object"
                log.verbose(f"{task_desc} by {method_desc}")
                log.verbose(f"llm_prompt_2_factory: {llm_prompt_2_factory}")
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
        output_name: str | None = None,
    ) -> PipeLLMOutput:
        content_generator_dry = ContentGeneratorDry()
        return await self._run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            content_generator=content_generator_dry,
        )

    @staticmethod
    async def get_output_structure_prompt(concept_string: str, is_with_preliminary_text: bool) -> str | None:
        concept = get_required_concept(concept_string=concept_string)
        output_class = get_class_registry().get_class(concept.structure_class_name)
        log.debug(f"get_output_structure_prompt for {concept_string} with {is_with_preliminary_text=}")
        log.debug(f"output_class: {output_class}")
        if not output_class:
            return None

        class_structure = StructurePrinter().get_type_structure(tp=output_class, base_class=StuffContent)

        if not class_structure:
            return None
        class_structure_str = "\n".join(class_structure)
        llm_config = get_config().cogt.llm_config
        if is_with_preliminary_text:
            template_source = llm_config.get_template(template_name="output_structure_prompt")
        else:
            template_source = llm_config.get_template(template_name="output_structure_prompt_no_preliminary_text")

        return await get_content_generator().make_templated_text(
            context={
                "class_structure_str": class_structure_str,
            },
            template=template_source,
            template_category=TemplateCategory.LLM_PROMPT,
        )
