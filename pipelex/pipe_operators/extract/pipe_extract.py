from typing import TYPE_CHECKING, Literal

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.extract.extract_setting import ExtractModelChoice, ExtractSetting
from pipelex.cogt.models.model_deck_check import check_extract_choice_with_deck
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import (
    get_content_generator,
    get_model_deck,
    get_native_concept,
)
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata

if TYPE_CHECKING:
    from pipelex.core.stuffs.page_content import PageContent


class PipeExtractOutput(PipeOutput):
    pass


class PipeExtract(PipeOperator[PipeExtractOutput]):
    type: Literal["PipeExtract"] = "PipeExtract"
    extract_choice: ExtractModelChoice | None
    should_caption_images: bool
    max_page_images: int | None
    should_include_page_views: bool
    page_views_dpi: int

    image_stuff_name: str | None = None
    document_stuff_name: str | None = None

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @override
    def required_variables(self) -> set[str]:
        return set(self.inputs.required_names)

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        if self.image_stuff_name is None and self.document_stuff_name is None:
            msg = "For PipeExtract you must provide either a document or an image or a concept that refines one of them"
            raise ValueError(msg)
        return self

    @override
    def validate_inputs_static(self):
        if self.extract_choice:
            try:
                check_extract_choice_with_deck(extract_choice=self.extract_choice)
            except ModelChoiceNotFoundError as exc:
                msg = f"Extract choice '{self.extract_choice}' was not found in the model deck"
                raise ValueError(msg) from exc

    @override
    def validate_inputs_with_library(self):
        pass

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        if self.output.concept != get_native_concept(native_concept=NativeConceptCode.PAGE):
            msg = f"PipeExtract output should be a Page concept, but is {self.output.concept.concept_ref}"
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=self.output.concept.concept_ref,
                required_concept_codes=[NativeConceptCode.PAGE.concept_ref],
            )

    @override
    async def _live_run_operator_pipe(
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
        elif self.document_stuff_name:
            document_stuff = working_memory.get_stuff_as_document(name=self.document_stuff_name)
            pdf_uri = document_stuff.url

        extract_choice: ExtractModelChoice = self.extract_choice or get_model_deck().extract_choice_default
        extract_setting: ExtractSetting = get_model_deck().get_extract_setting(extract_choice=extract_choice)

        # PLX-level max_page_images takes precedence if set, otherwise use ExtractSetting
        max_nb_images = self.max_page_images if self.max_page_images is not None else extract_setting.max_nb_images

        extract_job_params = ExtractJobParams(
            should_caption_images=self.should_caption_images,
            should_include_page_views=self.should_include_page_views,
            page_views_dpi=self.page_views_dpi,
            max_nb_images=max_nb_images,
            image_min_size=extract_setting.image_min_size,
        )
        extract_input = ExtractInput(
            image_uri=image_uri,
            document_uri=pdf_uri,
        )
        page_contents = await content_generator.make_extract_pages(
            extract_input=extract_input,
            extract_handle=extract_setting.model,
            job_metadata=job_metadata,
            extract_job_params=extract_job_params,
            extract_job_config=ExtractJobConfig(),
        )

        content: ListContent[PageContent] = ListContent(items=page_contents)

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output.concept,
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
