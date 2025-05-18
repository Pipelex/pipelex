# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import List, Optional

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex.cogt.ocr.ocr_engine_abstract import OCREngineAbstract
from pipelex.cogt.ocr.ocr_engine_factory import OCREngineFactory, OcrEngineName
from pipelex.config import get_config
from pipelex.core.pipe import PipeAbstract, update_job_metadata_for_pipe
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff_content import ImageContent, ListContent, TextAndImagesContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeDefinitionError
from pipelex.job_metadata import JobMetadata
from pipelex.libraries.pipelines.documents import PageContent
from pipelex.tools.utils.validation_utils import has_exactly_one_among_attributes_from_list


class PipeOCROutput(PipeOutput):
    pass


class PipeOCR(PipeAbstract):
    ocr_engine_name: Optional[OcrEngineName] = None
    image_stuff_name: Optional[str] = None
    pdf_stuff_name: Optional[str] = None
    should_add_screenshots: bool
    should_caption_images: bool

    @model_validator(mode="after")
    def validate_at_least_one_stuff_name(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["image_stuff_name", "pdf_stuff_name"]):
            raise PipeDefinitionError("At least one of 'image_stuff_name' or 'pdf_stuff_name' must be provided")
        return self

    @override
    @update_job_metadata_for_pipe
    async def run_pipe(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        pipe_code: str,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOCROutput:
        if not self.ocr_engine_name:
            self.ocr_engine_name = OcrEngineName(get_config().cogt.ocr_config.default_ocr_engine_name)

        ocr_engine: OCREngineAbstract = OCREngineFactory.make_ocr_engine(self.ocr_engine_name)

        if not self.output_concept_code:
            raise PipeDefinitionError("PipeOCR should have a non-None output_concept_code")

        if self.image_stuff_name:
            image_stuff = working_memory.get_stuff_as_image(name=self.image_stuff_name)
            ocr_output = await ocr_engine.make_ocr_output_from_image(
                image_uri=image_stuff.url,
                should_caption_image=self.should_caption_images,
            )
        elif self.pdf_stuff_name:
            pdf_stuff = working_memory.get_stuff_as_pdf(name=self.pdf_stuff_name)
            ocr_output = await ocr_engine.make_ocr_output_from_pdf(
                pdf_uri=pdf_stuff.url,
                should_caption_images=self.should_caption_images,
                should_add_screenshots=True,
            )
        else:
            raise PipeDefinitionError("PipeOCR should have a non-None image_stuff_name or pdf_stuff_name")

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

        pipe_output = PipeOCROutput(
            working_memory=working_memory,
        )
        return pipe_output
