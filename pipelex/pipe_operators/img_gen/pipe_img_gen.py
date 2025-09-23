from typing import List, Literal, Optional, Set, Union

from pydantic import Field, field_validator, model_validator
from typing_extensions import Self, override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobParams, OutputFormat, Quality
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.img_gen.img_gen_setting import ImgGenChoice, ImgGenSetting
from pipelex.cogt.models.model_deck_check import check_img_gen_choice_with_deck
from pipelex.config import StaticValidationReaction, get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NATIVE_CONCEPTS_DATA, NativeConceptEnum
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_input import PipeInputSpec
from pipelex.core.pipes.pipe_input_factory import PipeInputSpecFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import PipeOutputMultiplicity, PipeRunMode, PipeRunParams, output_multiplicity_to_apply
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_content import ImageContent, ListContent, StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.exceptions import (
    PipeDefinitionError,
    PipeInputError,
    PipeRunParamsError,
    StaticValidationError,
    StaticValidationErrorType,
    UnexpectedPipeDefinitionError,
    WorkingMemoryStuffNotFoundError,
)
from pipelex.hub import get_concept_provider, get_content_generator, get_model_deck
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipeline.job_metadata import JobMetadata


class PipeImgGenOutput(PipeOutput):
    @property
    def image_urls(self) -> List[str]:
        the_urls: List[str] = []
        content = self.main_stuff.content
        if isinstance(content, ListContent):
            items = self.main_stuff_as_items(item_type=ImageContent)
            the_urls = [item.url for item in items]
        elif isinstance(content, ImageContent):
            the_urls = [content.url]
        else:
            raise PipeRunParamsError(f"PipeImgGen output should be a ListContent or an ImageContent, got {type(content)}")
        return the_urls


DEFAULT_PROMPT_VAR_NAME = "prompt"


class PipeImgGen(PipeOperator):
    type: Literal["PipeImgGen"] = "PipeImgGen"
    img_gen_prompt: Optional[str] = None
    img_gen_prompt_var_name: Optional[str] = None

    # New ImgGenChoice pattern (like LLM)
    img_gen: Optional[ImgGenChoice] = None

    # Legacy individual settings (for backwards compatibility)
    img_gen_handle: Optional[str] = None
    quality: Optional[Quality] = Field(default=None, strict=False)
    nb_steps: Optional[int] = Field(default=None, gt=0)
    guidance_scale: Optional[float] = Field(default=None, gt=0)
    is_moderated: Optional[bool] = None
    safety_tolerance: Optional[int] = Field(default=None, ge=1, le=6)

    # One-time settings (not in ImgGenSetting)
    aspect_ratio: Optional[AspectRatio] = Field(default=None, strict=False)
    is_raw: Optional[bool] = None
    seed: Optional[Union[int, Literal["auto"]]] = None
    background: Optional[Background] = Field(default=None, strict=False)
    output_format: Optional[OutputFormat] = Field(default=None, strict=False)
    output_multiplicity: PipeOutputMultiplicity

    @field_validator("img_gen_prompt_var_name")
    @classmethod
    def validate_input_var_name_not_provided_as_attribute(cls, value: Optional[str]) -> Optional[str]:
        if value is not None:
            raise PipeDefinitionError("img_gen_prompt_var_name must be None before input validation")
        return value

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        self._validate_inputs()
        return self

    @override
    def validate_with_libraries(self):
        self._validate_inputs()
        if self.img_gen:
            check_img_gen_choice_with_deck(img_gen_choice=self.img_gen)

    @override
    def validate_output(self):
        if not get_concept_provider().is_compatible(
            tested_concept=self.output,
            wanted_concept=get_concept_provider().get_native_concept(native_concept=NativeConceptEnum.IMAGE),
            strict=True,
        ):
            raise PipeDefinitionError(
                f"The output of a ImgGen pipe must be compatible with the Image concept. "
                f"In the pipe '{self.code}' the output is '{self.output.concept_string}'"
            )

    @override
    def needed_inputs(self, visited_pipes: Optional[Set[str]] = None) -> PipeInputSpec:
        needed_inputs = PipeInputSpecFactory.make_empty()
        if self.img_gen_prompt:
            needed_inputs.add_requirement(
                variable_name="img_gen_prompt",
                concept=ConceptFactory.make_native_concept(
                    native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT],
                ),
            )
        else:
            for input_name, requirement in self.inputs.items:
                needed_inputs.add_requirement(variable_name=input_name, concept=requirement.concept)
        return needed_inputs

    @override
    def required_variables(self) -> Set[str]:
        if self.img_gen_prompt_var_name:
            return {self.img_gen_prompt_var_name}
        else:
            return {DEFAULT_PROMPT_VAR_NAME}

    def _validate_inputs(self):
        concept_provider = get_concept_provider()
        static_validation_config = get_config().pipelex.static_validation_config
        default_reaction = static_validation_config.default_reaction
        reactions = static_validation_config.reactions
        # check that we have either an img_gen_prompt passed as attribute or as a single text input
        if self.img_gen_prompt:
            if self.inputs.items:
                raise PipeDefinitionError("img_gen_prompt_var_name must be None if img_gen_prompt is provided")
            else:
                # we're good with the prompt provided as attribute
                return

        candidate_prompt_var_names: List[str] = []
        for input_name, requirement in self.inputs.items:
            log.debug(f"Validating input '{input_name}' with concept code '{requirement.concept.code}'")
            if concept_provider.is_compatible(
                tested_concept=requirement.concept,
                wanted_concept=ConceptFactory.make_native_concept(native_concept_data=NATIVE_CONCEPTS_DATA[NativeConceptEnum.TEXT]),
            ):
                self.img_gen_prompt_var_name = input_name
                candidate_prompt_var_names.append(input_name)
            else:
                inadequate_input_concept_error = StaticValidationError(
                    error_type=StaticValidationErrorType.INADEQUATE_INPUT_CONCEPT,
                    domain=self.domain,
                    pipe_code=self.code,
                    variable_names=[input_name],
                    provided_concept_code=requirement.concept.code,
                    explanation="Only a text input can be provided for image gen prompt",
                )
                match reactions.get(StaticValidationErrorType.INADEQUATE_INPUT_CONCEPT, default_reaction):
                    case StaticValidationReaction.IGNORE:
                        pass
                    case StaticValidationReaction.LOG:
                        log.error(inadequate_input_concept_error.desc())
                    case StaticValidationReaction.RAISE:
                        raise inadequate_input_concept_error
        if len(candidate_prompt_var_names) > 1:
            too_many_candidate_inputs_error = StaticValidationError(
                error_type=StaticValidationErrorType.TOO_MANY_CANDIDATE_INPUTS,
                domain=self.domain,
                pipe_code=self.code,
                variable_names=candidate_prompt_var_names,
                explanation="Only one text input can be provided for image gen prompt",
            )
            match reactions.get(StaticValidationErrorType.TOO_MANY_CANDIDATE_INPUTS, default_reaction):
                case StaticValidationReaction.IGNORE:
                    pass
                case StaticValidationReaction.LOG:
                    log.error(too_many_candidate_inputs_error.desc())
                case StaticValidationReaction.RAISE:
                    raise too_many_candidate_inputs_error
        elif len(candidate_prompt_var_names) == 0:
            missing_input_var_error = StaticValidationError(
                error_type=StaticValidationErrorType.MISSING_INPUT_VARIABLE,
                domain=self.domain,
                pipe_code=self.code,
                explanation="You must provide an image gen prompt either as attribute of the pipe or as a single text input",
            )
            match reactions.get(StaticValidationErrorType.MISSING_INPUT_VARIABLE, default_reaction):
                case StaticValidationReaction.IGNORE:
                    pass
                case StaticValidationReaction.LOG:
                    log.error(missing_input_var_error.desc())
                case StaticValidationReaction.RAISE:
                    raise missing_input_var_error
        else:
            self.img_gen_prompt_var_name = candidate_prompt_var_names[0]

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
        content_generator: Optional[ContentGeneratorProtocol] = None,
    ) -> PipeImgGenOutput:
        content_generator = content_generator or get_content_generator()

        multiplicity_resolution = output_multiplicity_to_apply(
            base_multiplicity=self.output_multiplicity or False,
            override_multiplicity=pipe_run_params.output_multiplicity,
        )
        applied_output_multiplicity = multiplicity_resolution.resolved_multiplicity

        log.debug("Getting image generation prompt from context")
        if self.img_gen_prompt:
            img_gen_prompt_text = self.img_gen_prompt
        elif stuff_name := self.img_gen_prompt_var_name:
            try:
                img_gen_prompt_text = working_memory.get_stuff_as_str(stuff_name)
            except WorkingMemoryStuffNotFoundError as exc:
                raise PipeInputError(f"Could not find a valid user image named '{stuff_name}' in the working_memory: {exc}") from exc
        else:
            raise UnexpectedPipeDefinitionError("You must provide an image gen prompt either as attribute of the pipe or as a single text input")

        img_gen_config = get_config().cogt.img_gen_config
        img_gen_param_defaults = img_gen_config.img_gen_param_defaults
        model_deck = get_model_deck()

        # Get ImgGenSetting either from img_gen choice or legacy settings
        img_gen_setting: ImgGenSetting
        if self.img_gen is not None:
            # New pattern: use img_gen choice (preset or inline setting)
            img_gen_setting = model_deck.get_img_gen_setting(self.img_gen)
        elif self.img_gen_handle is not None:
            # Legacy pattern: create ImgGenSetting from individual settings
            img_gen_setting = ImgGenSetting(
                img_gen_handle=self.img_gen_handle,
                quality=self.quality,
                nb_steps=self.nb_steps,
                guidance_scale=self.guidance_scale or img_gen_param_defaults.guidance_scale,
                is_moderated=self.is_moderated if self.is_moderated is not None else img_gen_param_defaults.is_moderated,
                safety_tolerance=self.safety_tolerance or img_gen_param_defaults.safety_tolerance,
            )
        else:
            # Use default from model deck
            img_gen_setting = model_deck.get_img_gen_setting(model_deck.img_gen_choice_default)

        # Process one-time settings
        seed_setting = self.seed or img_gen_param_defaults.seed
        seed: Optional[int]
        if isinstance(seed_setting, str) and seed_setting == "auto":
            seed = None
        else:
            seed = seed_setting

        # Build ImggJobParams from ImgGenSetting + one-time settings
        img_gen_job_params = ImgGenJobParams(
            aspect_ratio=self.aspect_ratio or img_gen_param_defaults.aspect_ratio,
            background=self.background or img_gen_param_defaults.background,
            quality=img_gen_setting.quality,
            nb_steps=img_gen_setting.nb_steps,
            guidance_scale=img_gen_setting.guidance_scale,
            is_moderated=img_gen_setting.is_moderated,
            safety_tolerance=img_gen_setting.safety_tolerance,
            is_raw=self.is_raw if self.is_raw is not None else img_gen_param_defaults.is_raw,
            output_format=self.output_format or img_gen_param_defaults.output_format,
            seed=seed,
        )
        # Get the image generation handle
        img_gen_handle = img_gen_setting.img_gen_handle
        log.debug(f"Using img_gen handle: {img_gen_handle}")

        the_content: StuffContent
        image_urls: List[str] = []
        nb_images: int
        if isinstance(applied_output_multiplicity, bool):
            if self.output_multiplicity:
                msg = "Cannot guess how many images to generate if multiplicity is just True."
                msg += f" Got PipeImgGen.output_multiplicity = {self.output_multiplicity},"
                msg += f" and pipe_run_params.output_multiplicity = {pipe_run_params.output_multiplicity}."
                msg += f" Tried to apply applied_output_multiplicity = {applied_output_multiplicity}."
                raise PipeRunParamsError(msg)
            else:
                nb_images = 1
        elif isinstance(applied_output_multiplicity, int):
            nb_images = applied_output_multiplicity
        else:
            nb_images = 1

        if nb_images > 1:
            generated_image_list = await content_generator.make_image_list(
                job_metadata=job_metadata,
                img_gen_handle=img_gen_handle,
                img_gen_prompt=ImgGenPrompt(
                    positive_text=img_gen_prompt_text,
                ),
                nb_images=nb_images,
                img_gen_job_params=img_gen_job_params,
                img_gen_job_config=img_gen_config.img_gen_job_config,
            )
            image_content_items: List[StuffContent] = []
            for generated_image in generated_image_list:
                image_content_items.append(
                    ImageContent(
                        url=generated_image.url,
                        source_prompt=img_gen_prompt_text,
                    )
                )
                image_urls.append(generated_image.url)
            the_content = ListContent(
                items=image_content_items,
            )
            log.verbose(the_content, title="List of image contents")
        else:
            generated_image = await content_generator.make_single_image(
                job_metadata=job_metadata,
                img_gen_handle=img_gen_handle,
                img_gen_prompt=ImgGenPrompt(
                    positive_text=img_gen_prompt_text,
                ),
                img_gen_job_params=img_gen_job_params,
                img_gen_job_config=img_gen_config.img_gen_job_config,
            )

            generated_image_url = generated_image.url
            image_urls = [generated_image_url]

            the_content = ImageContent(
                url=generated_image_url,
                source_prompt=img_gen_prompt_text,
            )
            log.verbose(the_content, title="Single image content")

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output,
            content=the_content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        pipe_output = PipeImgGenOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )
        return pipe_output

    @override
    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        log.debug(f"PipeImgGen: dry run operator pipe: {self.code}")
        content_generator_dry = ContentGeneratorDry()
        pipe_output = await self._run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params or PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.DRY),
            output_name=output_name,
            content_generator=content_generator_dry,
        )
        return pipe_output
