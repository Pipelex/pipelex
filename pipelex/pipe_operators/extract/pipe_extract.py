from typing import Literal

from pydantic import model_validator
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.models.model_deck_check import check_extract_choice_with_deck
from pipelex.config import StaticValidationReaction, get_config
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.exceptions import (
    PipeDefinitionError,
    StaticValidationError,
    StaticValidationErrorType,
)
from pipelex.hub import (
    get_concept_library,
    get_content_generator,
    get_model_deck,
    get_native_concept,
)
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunMode, PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer
from pipelex.types import Self


class PipeExtractOutput(PipeOutput):
    pass


class PipeExtract(PipeOperator[PipeExtractOutput]):
    type: Literal["PipeExtract"] = "PipeExtract"
    extract_choice: ExtractModelChoice | None
    should_caption_images: bool
    should_include_images: bool
    should_include_page_views: bool
    page_views_dpi: int

    image_stuff_name: str | None = None
    pdf_stuff_name: str | None = None

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        self._validate_inputs()
        return self

    @override
    def validate_with_libraries(self):
        self._validate_inputs()
        if self.extract_choice:
            check_extract_choice_with_deck(extract_choice=self.extract_choice)

    @override
    def required_variables(self) -> set[str]:
        return set(self.inputs.required_names)

    @override
    def validate_output(self):
        if self.output != get_native_concept(native_concept=NativeConceptCode.PAGE):
            msg = f"PipeExtract output should be a Page concept, but is {self.output.concept_string}"
            raise PipeDefinitionError(msg)

    def _validate_inputs(self):
        concept_library = get_concept_library()
        static_validation_config = get_config().pipelex.static_validation_config
        default_reaction = static_validation_config.default_reaction
        reactions = static_validation_config.reactions

        # check that we have exactly one input
        nb_inputs = self.inputs.nb_inputs
        if nb_inputs > 1:
            too_many_candidate_inputs_error = StaticValidationError(
                error_type=StaticValidationErrorType.TOO_MANY_CANDIDATE_INPUTS,
                domain=self.domain,
                pipe_code=self.code,
                variable_names=self.inputs.variables,
                explanation="Only one image or pdf can be provided for OCR",
            )
            match reactions.get(StaticValidationErrorType.TOO_MANY_CANDIDATE_INPUTS, default_reaction):
                case StaticValidationReaction.IGNORE:
                    pass
                case StaticValidationReaction.LOG:
                    log.error(too_many_candidate_inputs_error.desc())
                case StaticValidationReaction.RAISE:
                    raise too_many_candidate_inputs_error
        elif nb_inputs < 1:
            missing_input_var_error = StaticValidationError(
                error_type=StaticValidationErrorType.MISSING_INPUT_VARIABLE,
                domain=self.domain,
                pipe_code=self.code,
                explanation="For OCR you must provide either a pdf or an image or a concept that refines one of them",
            )
            match reactions.get(StaticValidationErrorType.MISSING_INPUT_VARIABLE, default_reaction):
                case StaticValidationReaction.IGNORE:
                    pass
                case StaticValidationReaction.LOG:
                    log.error(missing_input_var_error.desc())
                case StaticValidationReaction.RAISE:
                    raise missing_input_var_error

        # We have confirmed right above that we have exactly one input
        # get input_name, requirement from single item in inputs
        input_name, requirement = self.inputs.items[0]
        log.debug(f"Validating input '{input_name}' with concept code '{requirement.concept.code}'")
        if concept_library.is_compatible(
            tested_concept=requirement.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.IMAGE),
            strict=True,
        ):
            self.image_stuff_name = input_name
        elif concept_library.is_compatible(
            tested_concept=requirement.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.PDF),
            strict=True,
        ):
            self.pdf_stuff_name = input_name
        else:
            inadequate_input_concept_error = StaticValidationError(
                error_type=StaticValidationErrorType.INADEQUATE_INPUT_CONCEPT,
                domain=self.domain,
                pipe_code=self.code,
                variable_names=[input_name],
                provided_concept_code=requirement.concept.code,
                explanation="For PipeExtract you must provide either a pdf or an image or a concept that refines one of them",
            )
            match reactions.get(StaticValidationErrorType.INADEQUATE_INPUT_CONCEPT, default_reaction):
                case StaticValidationReaction.IGNORE:
                    pass
                case StaticValidationReaction.LOG:
                    log.error(inadequate_input_concept_error.desc())
                case StaticValidationReaction.RAISE:
                    raise inadequate_input_concept_error

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputRequirements:
        return self.inputs

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
    ) -> PipeExtractOutput:
        content_generator = content_generator or get_content_generator()

        image_uri: str | None = None
        pdf_uri: str | None = None
        if self.image_stuff_name:
            image_stuff = working_memory.get_stuff_as_image(name=self.image_stuff_name)
            image_uri = image_stuff.url
        elif self.pdf_stuff_name:
            pdf_stuff = working_memory.get_stuff_as_pdf(name=self.pdf_stuff_name)
            pdf_uri = pdf_stuff.url
        else:
            msg = "PipeExtract should have a non-None image_stuff_name or pdf_stuff_name"
            raise PipeDefinitionError(msg)

        extract_choice: ExtractModelChoice = self.extract_choice or get_model_deck().extract_choice_default
        extract_setting: ExtractSetting = get_model_deck().get_extract_setting(extract_choice=extract_choice)

        extract_job_params = ExtractJobParams(
            should_include_images=self.should_include_images,
            should_caption_images=self.should_caption_images,
            should_include_page_views=self.should_include_page_views,
            page_views_dpi=self.page_views_dpi,
            max_nb_images=extract_setting.max_nb_images,
            image_min_size=extract_setting.image_min_size,
        )
        extract_input = ExtractInput(
            image_uri=image_uri,
            pdf_uri=pdf_uri,
        )
        extract_output = await content_generator.make_extract_pages(
            extract_input=extract_input,
            extract_handle=extract_setting.model,
            job_metadata=job_metadata,
            extract_job_params=extract_job_params,
            extract_job_config=ExtractJobConfig(),
        )

        # Build the output stuff, which is a list of page contents
        page_view_contents: list[ImageContent] = []
        if self.should_include_page_views:
            log.debug(f"should_include_page_views: {self.should_include_page_views}, pdf_uri: {pdf_uri}, image_uri: {image_uri}")
            if pdf_uri:
                page_view_contents.extend(
                    ImageContent.make_from_extracted_image(extracted_image=page.page_view) for page in extract_output.pages.values() if page.page_view
                )
                log.debug(f"page_view_contents: {page_view_contents}")
                needs_to_generate_page_views: bool
                if len(page_view_contents) == 0:
                    log.debug("No page views found in the OCR output")
                    needs_to_generate_page_views = True
                elif len(page_view_contents) < len(extract_output.pages):
                    log.warning(f"Only {len(page_view_contents)} page found in the OCR output, but {len(extract_output.pages)} pages")
                    needs_to_generate_page_views = True
                else:
                    log.debug("All page views found in the OCR output")
                    needs_to_generate_page_views = False

                if needs_to_generate_page_views:
                    page_views = await pypdfium2_renderer.render_pdf_pages_from_uri(pdf_uri=pdf_uri, dpi=self.page_views_dpi)
                    page_view_contents = [ImageContent.make_from_image(image=img) for img in page_views]
            elif image_uri:
                page_view_contents = [ImageContent(url=image_uri)]

        page_contents: list[PageContent] = []
        for page_index, page in extract_output.pages.items():
            images = [ImageContent.make_from_extracted_image(extracted_image=img) for img in page.extracted_images]
            log.debug(f"images: {images}, page_view_contents: {page_view_contents}, index: {page_index}")
            page_view = page_view_contents[page_index - 1] if self.should_include_page_views else None
            page_contents.append(
                PageContent(
                    text_and_images=TextAndImagesContent(
                        text=TextContent(text=page.text) if page.text else None,
                        images=images,
                    ),
                    page_view=page_view,
                ),
            )

        content: ListContent[PageContent] = ListContent(items=page_contents)

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output,
            content=content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        return PipeExtractOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeExtractOutput:
        log.debug(f"PipeExtract: dry run operator pipe: {self.code}")
        if pipe_run_params.run_mode != PipeRunMode.DRY:
            msg = f"Running pipe '{self.code}' (PipeExtract) _dry_run_operator_pipe() in non-dry mode is not allowed."
            raise PipeDefinitionError(msg)

        content_generator_dry = ContentGeneratorDry()
        return await self._run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            content_generator=content_generator_dry,
        )
