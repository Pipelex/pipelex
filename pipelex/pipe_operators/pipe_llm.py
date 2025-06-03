from typing import List, Optional, Set, Type, cast

from kajson.class_registry import class_registry
from pydantic import model_validator
from typing_extensions import Self, override

from pipelex import log
from pipelex.cogt.llm.llm_models.llm_deck import LLMSettingChoices
from pipelex.cogt.llm.llm_models.llm_deck_check import check_llm_setting_with_deck
from pipelex.cogt.llm.llm_models.llm_setting import LLMSetting
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_factory_abstract import LLMPromptFactoryAbstract
from pipelex.config import get_config
from pipelex.core.concept_factory import ConceptFactory
from pipelex.core.concept_native import NativeConcept, NativeConceptClass
from pipelex.core.domain import Domain, SpecialDomain
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import (
    PipeOutputMultiplicity,
    PipeRunParamKey,
    PipeRunParams,
    output_multiplicity_to_apply,
)
from pipelex.core.stuff_content import ListContent, StuffContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeDefinitionError, PipeExecutionError
from pipelex.hub import (
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
    def validate_output_concept_consistency(self) -> Self:
        if self.structuring_method is not None:
            output_concept = get_required_concept(concept_code=self.output_concept_code)
            if output_concept.structure_class_name == NativeConceptClass.TEXT:
                raise PipeDefinitionError(f"Output concept '{self.output_concept_code}' is a TextConcept, so it cannot be structured")
        return self

    @override
    def validate_with_libraries(self):
        if self.input_concept_code and get_concept_provider().is_compatible_by_concept_code(
            tested_concept_code=self.input_concept_code,
            wanted_concept_code=NativeConcept.IMAGE.code,
        ):
            if not self.pipe_llm_prompt.user_images:
                raise PipeDefinitionError(f"No user images provided for concept '{self.input_concept_code}' but it's required")
        self.pipe_llm_prompt.validate_with_libraries()
        if self.prompt_template_to_structure:
            get_template(template_name=self.prompt_template_to_structure)
        if self.system_prompt_to_structure:
            get_template(template_name=self.system_prompt_to_structure)
        if self.llm_choices:
            for llm_setting in self.llm_choices.list_used_presets():
                check_llm_setting_with_deck(llm_setting_or_preset_id=llm_setting)

    @property
    def llm_setting_main(self) -> LLMSetting:
        return get_llm_deck().get_llm_setting_for_text(override=self.llm_choices)

    @property
    def llm_setting_for_object(self) -> LLMSetting:
        return get_llm_deck().get_llm_setting_for_object(override=self.llm_choices)

    @property
    def llm_setting_for_object_direct(self) -> LLMSetting:
        return get_llm_deck().get_llm_setting_for_object_direct(override=self.llm_choices)

    @property
    def llm_setting_for_object_list(self) -> LLMSetting:
        return get_llm_deck().get_llm_setting_for_object_list(override=self.llm_choices)

    @property
    def llm_setting_for_object_list_direct(self) -> LLMSetting:
        return get_llm_deck().get_llm_setting_for_object_list_direct(override=self.llm_choices)

    @override
    def required_variables(self) -> Set[str]:
        required_variables: Set[str] = set()
        required_variables.update(self.pipe_llm_prompt.required_variables())
        return required_variables

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeLLMOutput:
        # interpret / unwrap the arguments
        log.debug(f"PipeLLM pipe_code = {self.code}")
        if self.output_concept_code == ConceptFactory.make_concept_code(
            SpecialDomain.NATIVE,
            NativeConcept.DYNAMIC.code,
        ):
            # TODO: This DYNAMIC_OUTPUT_CONCEPT should not be a field in the params attribute of PipeRunParams.
            # It should be an attribute of PipeRunParams.
            output_concept_code = pipe_run_params.dynamic_output_concept_code or pipe_run_params.params.get(PipeRunParamKey.DYNAMIC_OUTPUT_CONCEPT)
            if not output_concept_code:
                raise RuntimeError(f"No output concept code provided for dynamic output pipe '{self.code}'")
        else:
            output_concept_code = self.output_concept_code

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

        if not self.pipe_llm_prompt.prompting_style:
            llm_deck = get_llm_deck()
            llm_model = llm_deck.find_llm_model(llm_handle=self.llm_setting_main.llm_handle)
            llm_family = llm_model.llm_family
            if self.llm_setting_main.prompting_target:
                log.dev(f"prompting_target for '{self.llm_setting_main.llm_handle}' from setting: {self.llm_setting_main}")
            else:
                log.dev(f"prompting_target for '{self.llm_setting_main.llm_handle}' from llm_family: {llm_family}")
            prompting_target = self.llm_setting_main.prompting_target or llm_family.prompting_target
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

        if input_concept_code := self.input_concept_code:
            if (
                get_concept_provider().is_compatible_by_concept_code(
                    tested_concept_code=input_concept_code,
                    wanted_concept_code=NativeConcept.IMAGE.code,
                )
                and not llm_prompt_1.user_images
            ):
                raise PipeExecutionError(
                    f"No user images provided in the prompt with input concept '{input_concept_code}' but it's required for pipe '{self.code}'"
                )

        the_content: StuffContent
        if output_concept.structure_class_name == NativeConceptClass.TEXT and not is_multiple_output:
            log.debug(f"PipeLLM generating a single text output: {self.class_name}_gen_text")
            generated_text: str = await get_content_generator().make_llm_text(
                job_metadata=job_metadata,
                llm_prompt_for_text=llm_prompt_1,
                llm_setting_main=self.llm_setting_main,
                wfid=f"{self.class_name}_gen_text",
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
                llm_prompt_1=llm_prompt_1,
                llm_prompt_2_factory=llm_prompt_2_factory,
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
        )
        return pipe_output

    async def _llm_gen_object_stuff_content(
        self,
        job_metadata: JobMetadata,
        is_multiple_output: bool,
        fixed_nb_output: Optional[int],
        output_class_name: str,
        llm_prompt_1: LLMPrompt,
        llm_prompt_2_factory: Optional[LLMPromptFactoryAbstract],
    ) -> StuffContent:
        content_class: Type[StuffContent] = class_registry.get_required_subclass(name=output_class_name, base_class=StuffContent)
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

                generated_objects = await get_content_generator().make_text_then_object_list(
                    job_metadata=job_metadata,
                    object_class=content_class,
                    llm_prompt_for_text=llm_prompt_1,
                    llm_setting_main=self.llm_setting_main,
                    llm_prompt_factory_for_object_list=llm_prompt_2_factory,
                    llm_setting_for_object_list=self.llm_setting_for_object_list,
                    wfid=task_desc,
                )
            else:
                # We're generating a list of objects directly
                method_desc = "object_direct"
                log.dev(f"{task_desc} by {method_desc}, content_class={content_class.__name__}")
                generated_objects = await get_content_generator().make_object_list_direct(
                    job_metadata=job_metadata,
                    object_class=content_class,
                    llm_prompt_for_object_list=llm_prompt_1,
                    llm_setting_for_object_list=self.llm_setting_for_object_list_direct,
                    wfid=task_desc,
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
                generated_object = await get_content_generator().make_text_then_object(
                    job_metadata=job_metadata,
                    object_class=content_class,
                    llm_prompt_for_text=llm_prompt_1,
                    llm_setting_main=self.llm_setting_main,
                    llm_prompt_factory_for_object=llm_prompt_2_factory,
                    llm_setting_for_object=self.llm_setting_for_object,
                    wfid=task_desc,
                )
            else:
                # We're generating a single object directly
                method_desc = "object_direct"
                log.verbose(f"{task_desc} by {method_desc}, content_class={content_class.__name__}")
                generated_object = await get_content_generator().make_object_direct(
                    job_metadata=job_metadata,
                    object_class=content_class,
                    llm_prompt_for_object=llm_prompt_1,
                    llm_setting_for_object=self.llm_setting_for_object_direct,
                    wfid=task_desc,
                )
            the_content = generated_object

        return the_content
