# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import List, Optional

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex.cogt.ocr.ocr_engine import OcrEngine
from pipelex.cogt.ocr.ocr_handle import OcrHandle
from pipelex.cogt.ocr.ocr_input import OcrInput
from pipelex.cogt.ocr.ocr_job_components import OcrJobConfig, OcrJobParams
from pipelex.core.pipe import PipeAbstract, update_job_metadata_for_pipe
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff_content import ImageContent, ListContent, PageContent, TextAndImagesContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_content_generator
from pipelex.job_metadata import JobMetadata
from pipelex.tools.utils.validation_utils import has_exactly_one_among_attributes_from_list


class PipeOcrOutput(PipeOutput):
    pass


class PipeOcr(PipeAbstract):
    ocr_engine: Optional[OcrEngine] = None
    image_stuff_name: Optional[str] = None
    pdf_stuff_name: Optional[str] = None
    should_add_screenshots: bool
    should_caption_images: bool

    @model_validator(mode="after")
    def validate_exactly_one_input_stuff_name(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["image_stuff_name", "pdf_stuff_name"]):
            raise PipeDefinitionError("Exactly one of 'image_stuff_name' or 'pdf_stuff_name' must be provided")
        return self

    @override
    @update_job_metadata_for_pipe
    async def run_pipe(  # pyright: ignore[reportIncompatibleMethodOverride]
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
        ocr_job_params = OcrJobParams.make_default_ocr_job_params()
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
        page_contents: List[PageContent] = []
        for _, page in ocr_output.pages.items():
            page_contents.append(
                PageContent(
                    text_and_images=TextAndImagesContent(
                        text=TextContent(text=page.text) if page.text else None,
                        images=[ImageContent(url=image.uri) for image in page.images],
                    ),
                    screenshot=ImageContent(url=page.screenshot.uri) if page.screenshot else None,
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
