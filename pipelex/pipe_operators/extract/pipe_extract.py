from typing import TYPE_CHECKING, Any, Literal

from pydantic import model_validator
from typing_extensions import Self, override

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
from pipelex.interpreter_hub import get_concept_library, get_native_concept
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.runtime_hub import get_content_generator, get_model_deck
from pipelex.system.job_metadata import JobMetadata

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
    page_views_dpi: int | None
    render_js: bool | None = None
    include_raw_html: bool | None = None

    image_stuff_name: str | None = None
    document_stuff_name: str | None = None

    @override
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @override
    def required_variables(self) -> set[str]:
        return set(self.inputs.declared_names)

    @model_validator(mode="after")
    def validate_fields(self) -> Self:
        if self.image_stuff_name is None and self.document_stuff_name is None:
            msg = "For PipeExtract you must provide either a Document or an Image or a concept that refines one of them"
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
        the_single_input = self.inputs.get_single_stuff_spec()
        image_concept = get_native_concept(native_concept=NativeConceptCode.IMAGE)
        document_concept = get_native_concept(native_concept=NativeConceptCode.DOCUMENT)
        concept_library = get_concept_library()
        if concept_library.is_compatible(tested_concept=the_single_input.concept, wanted_concept=image_concept, strict=True):
            # it's an image, we can't accept documnt-related fields
            if self.should_caption_images:
                msg = "PipeExtract with image input cannot have should_caption_images set to True"
                raise ValueError(msg)
            if self.should_include_page_views:
                msg = "PipeExtract with image input cannot have should_include_page_views set to True"
                raise ValueError(msg)
            if self.page_views_dpi is not None:
                msg = "PipeExtract with image input cannot have page_views_dpi set"
                raise ValueError(msg)
            if self.max_page_images is not None:
                msg = "PipeExtract with image input cannot have max_page_images set"
                raise ValueError(msg)
        elif not concept_library.is_compatible(tested_concept=the_single_input.concept, wanted_concept=document_concept, strict=True):
            msg = (
                "The input to PipeExtract must be an image or a document (or a concept that refines one of them), "
                f"but is {the_single_input.concept.concept_ref}"
            )
            raise TypeError(msg)

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
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeExtractOutput:
        content_generator = get_content_generator()

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

        # MTHDS-level max_page_images takes precedence if set, otherwise use ExtractSetting
        max_nb_images = self.max_page_images if self.max_page_images is not None else extract_setting.max_nb_images

        extract_job_params = ExtractJobParams(
            should_caption_images=self.should_caption_images,
            should_include_page_views=self.should_include_page_views,
            page_views_dpi=self.page_views_dpi,
            max_nb_images=max_nb_images,
            image_min_size=extract_setting.image_min_size,
            render_js=self.render_js,
            include_raw_html=self.include_raw_html,
        )
        extract_input = ExtractInput(
            image_uri=image_uri,
            document_uri=pdf_uri,
        )
        page_contents = await content_generator.make_extract_pages(
            extract_input=extract_input,
            cogt_run_params=pipe_run_params.cogt_run_params,
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

        # Capture execution data for the graph tracer
        execution_data_dict: dict[str, Any] = {
            "resolved_model": extract_setting.model,
            "document_stuff_name": self.document_stuff_name,
            "should_caption_images": self.should_caption_images,
            "should_include_page_views": self.should_include_page_views,
        }

        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
        return PipeExtractOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

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
