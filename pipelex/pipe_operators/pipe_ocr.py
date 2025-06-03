from typing import List, Optional

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex import log
from pipelex.cogt.ocr.ocr_engine import OcrEngine
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff_content import ImageContent, ListContent, PageContent, TextAndImagesContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_content_generator
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.pdf.pypdfium2_renderer import pypdfium2_renderer
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list


class PipeOcrOutput(PipeOutput):
    pass


class PipeOcr(PipeOperator):
    ocr_engine: Optional[OcrEngine] = None
    image_stuff_name: Optional[str] = None
    pdf_stuff_name: Optional[str] = None
    should_caption_images: bool
    should_include_images: bool
    should_include_page_views: bool
    page_views_dpi: int

    @model_validator(mode="after")
    def validate_exactly_one_input_stuff_name(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["image_stuff_name", "pdf_stuff_name"]):
            raise PipeDefinitionError("Exactly one of 'image_stuff_name' or 'pdf_stuff_name' must be provided")
        return self

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOcrOutput:
        if not self.output_concept_code:
            raise PipeDefinitionError("PipeOcr should have a non-None output_concept_code")

        image_uri: Optional[str] = None
        pdf_uri: Optional[str] = None
        if self.image_stuff_name:
            image_stuff = working_memory.get_stuff_as_image(name=self.image_stuff_name)
            image_uri = image_stuff.url
        elif self.pdf_stuff_name:
            pdf_stuff = working_memory.get_stuff_as_pdf(name=self.pdf_stuff_name)
            pdf_uri = pdf_stuff.url
        else:
            raise PipeDefinitionError("PipeOcr should have a non-None image_stuff_name or pdf_stuff_name")

        ocr_handle = OcrHandle.MISTRAL_OCR
        ocr_job_params = OcrJobParams(
            should_include_images=self.should_include_images,
            should_caption_images=self.should_caption_images,
            should_include_page_views=self.should_include_page_views,
            page_views_dpi=self.page_views_dpi,
        )
        ocr_input = OcrInput(
            image_uri=image_uri,
            pdf_uri=pdf_uri,
        )
        ocr_output = await get_content_generator().make_ocr_extract_pages(
            ocr_input=ocr_input,
            ocr_handle=ocr_handle,
            job_metadata=job_metadata,
            ocr_job_params=ocr_job_params,
            ocr_job_config=OcrJobConfig(),
        )

        # Build the output stuff, which is a list of page contents
        page_view_contents: List[ImageContent] = []
        if self.should_include_page_views:
            if pdf_uri:
                for page in ocr_output.pages.values():
                    if page.page_view:
                        page_view_contents.append(ImageContent.make_from_extracted_image(extracted_image=page.page_view))
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

        page_contents: List[PageContent] = []
        for page_index, page in ocr_output.pages.items():
            images = [ImageContent.make_from_extracted_image(extracted_image=img) for img in page.extracted_images]
            page_view = page_view_contents[page_index] if self.should_include_page_views else None
            page_contents.append(
                PageContent(
                    text_and_images=TextAndImagesContent(
                        text=TextContent(text=page.text) if page.text else None,
                        images=images,
                    ),
                    page_view=page_view,
                )
            )

        content: ListContent[PageContent] = ListContent(items=page_contents)

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept_code=self.output_concept_code,
            content=content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        pipe_output = PipeOcrOutput(
            working_memory=working_memory,
        )
        return pipe_output
