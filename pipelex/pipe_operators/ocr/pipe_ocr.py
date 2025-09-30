from typing import Literal

from pydantic import model_validator
from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.models.model_deck_check import check_ocr_choice_with_deck
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams
from pipelex.cogt.ocr.ocr_setting import OcrChoice, OcrSetting
from pipelex.config import StaticValidationReaction, get_config
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_input import PipeInputSpec
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import PipeRunMode, PipeRunParams
from pipelex.core.stuffs.stuff_content import ImageContent, ListContent, PageContent, TextAndImagesContent, TextContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.exceptions import (
    PipeDefinitionError,
    StaticValidationError,
    StaticValidationErrorType,
)
from pipelex.hub import (
    get_concept_provider,
    get_content_generator,
    get_model_deck,
)
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer
from pipelex.types import Self


class PipeOcrOutput(PipeOutput):
    pass


class PipeOcr(PipeOperator[PipeOcrOutput]):
    type: Literal["PipeOcr"] = "PipeOcr"
    ocr_choice: OcrChoice | None
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
        if self.ocr_choice:
            check_ocr_choice_with_deck(ocr_choice=self.ocr_choice)

    @override
    def required_variables(self) -> set[str]:
        return set(self.inputs.required_names)

    @override
    def validate_output(self):
        if self.output != get_concept_provider().get_native_concept(native_concept=NativeConceptEnum.PAGE):
            msg = f"PipeOcr output should be a Page concept, but is {self.output.concept_string}"
            raise PipeDefinitionError(msg)

    def _validate_inputs(self):
        concept_provider = get_concept_provider()
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
        if concept_provider.is_compatible(
            tested_concept=requirement.concept,
            wanted_concept=concept_provider.get_native_concept(native_concept=NativeConceptEnum.IMAGE),
            strict=True,
        ):
            self.image_stuff_name = input_name
        elif concept_provider.is_compatible(
            tested_concept=requirement.concept,
            wanted_concept=concept_provider.get_native_concept(native_concept=NativeConceptEnum.PDF),
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
                explanation="For PipeOcr you must provide either a pdf or an image or a concept that refines one of them",
            )
            match reactions.get(StaticValidationErrorType.INADEQUATE_INPUT_CONCEPT, default_reaction):
                case StaticValidationReaction.IGNORE:
                    pass
                case StaticValidationReaction.LOG:
                    log.error(inadequate_input_concept_error.desc())
                case StaticValidationReaction.RAISE:
                    raise inadequate_input_concept_error

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> PipeInputSpec:
        return self.inputs

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        content_generator: ContentGeneratorProtocol | None = None,
    ) -> PipeOcrOutput:
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
            msg = "PipeOcr should have a non-None image_stuff_name or pdf_stuff_name"
            raise PipeDefinitionError(msg)

        ocr_choice: OcrChoice = self.ocr_choice or get_model_deck().ocr_choice_default
        ocr_setting: OcrSetting = get_model_deck().get_ocr_setting(ocr_choice=ocr_choice)

        ocr_job_params = OcrJobParams(
            should_include_images=self.should_include_images,
            should_caption_images=self.should_caption_images,
            should_include_page_views=self.should_include_page_views,
            page_views_dpi=self.page_views_dpi,
            max_nb_images=ocr_setting.max_nb_images,
            image_min_size=ocr_setting.image_min_size,
        )
        ocr_input = OcrInput(
            image_uri=image_uri,
            pdf_uri=pdf_uri,
        )
        ocr_output = await content_generator.make_ocr_extract_pages(
            ocr_input=ocr_input,
            ocr_handle=ocr_setting.ocr_handle,
            job_metadata=job_metadata,
            ocr_job_params=ocr_job_params,
            ocr_job_config=OcrJobConfig(),
        )

        # Build the output stuff, which is a list of page contents
        page_view_contents: list[ImageContent] = []
        if self.should_include_page_views:
            log.debug(f"should_include_page_views: {self.should_include_page_views}, pdf_uri: {pdf_uri}, image_uri: {image_uri}")
            if pdf_uri:
                page_view_contents.extend(
                    ImageContent.make_from_extracted_image(extracted_image=page.page_view) for page in ocr_output.pages.values() if page.page_view
                )
                log.debug(f"page_view_contents: {page_view_contents}")
                needs_to_generate_page_views: bool
                if len(page_view_contents) == 0:
                    log.debug("No page views found in the OCR output")
                    needs_to_generate_page_views = True
                elif len(page_view_contents) < len(ocr_output.pages):
                    log.warning(f"Only {len(page_view_contents)} page found in the OCR output, but {len(ocr_output.pages)} pages")
                    needs_to_generate_page_views = True
                else:
                    log.debug("All page views found in the OCR output")
                    needs_to_generate_page_views = False

                if needs_to_generate_page_views:
                    page_views = await pypdfium2_renderer.render_pdf_pages_from_uri(pdf_uri=pdf_uri, dpi=self.page_views_dpi)
                    page_view_contents = [ImageContent.make_from_image(image=img) for img in page_views]
            elif image_uri:
                page_view_contents = [ImageContent.make_from_str(str_value=image_uri)]

        page_contents: list[PageContent] = []
        for page_index, page in ocr_output.pages.items():
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

        return PipeOcrOutput(
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
    ) -> PipeOcrOutput:
        log.debug(f"PipeOcr: dry run operator pipe: {self.code}")
        if pipe_run_params.run_mode != PipeRunMode.DRY:
            msg = f"Running pipe '{self.code}' (PipeOcr) _dry_run_operator_pipe() in non-dry mode is not allowed."
            raise PipeDefinitionError(msg)

        content_generator_dry = ContentGeneratorDry()
        return await self._run_operator_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            content_generator=content_generator_dry,
        )
