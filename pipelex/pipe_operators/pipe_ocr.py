# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex.cogt.ocr.ocr_engine_abstract import OCREngineAbstract
from pipelex.cogt.ocr.ocr_engine_factory import OCREngineFactory
from pipelex.core.pipe import PipeAbstract, update_job_metadata_for_pipe
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff_content import ImageContent, ListContent, TextAndImageContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.job_metadata import JobMetadata
from pipelex.libraries.pipelines.ocr import PageContent
from pipelex.tools.utils.path_utils import clarify_path_or_url


class PipeOCROutput(PipeOutput):
    pass


class PipeOCRInputError(ValueError):
    pass


class PipeOCR(PipeAbstract):
    image_stuff_name: Optional[str] = None
    document_stuff_name: Optional[str] = None
    ocr_engine_name: Optional[str] = None

    @model_validator(mode="after")
    def validate_at_least_one_stuff_name(self) -> Self:
        if self.image_stuff_name is None and self.document_stuff_name is None:
            raise PipeOCRInputError("At least one of 'image_stuff_name' or 'document_stuff_name' must be provided")
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
        # TODO:

        ocr_engine: OCREngineAbstract = OCREngineFactory.make_ocr_engine()

        if not self.output_concept_code:
            raise PipeOCRInputError("PipeOCR should have a non-None output_concept_code")

        if self.image_stuff_name:
            image_stuff = working_memory.get_stuff(name=self.image_stuff_name)
            image_url = image_stuff.as_image.url
            image_path, url = clarify_path_or_url(path_or_url=image_url)  # pyright: ignore
            if not image_stuff.is_image:
                raise PipeOCRInputError(f"Image stuff '{self.image_stuff_name}' is not an image")
            ocr_output = await ocr_engine.extraction_from_image(
                image_path=image_path,
                image_url=url,
            )

        elif self.document_stuff_name:
            document_stuff = working_memory.get_stuff(name=self.document_stuff_name)
            document_url = document_stuff.as_pdf.url
            document_path, url = clarify_path_or_url(path_or_url=document_url)  # pyright: ignore
            if not document_stuff.is_pdf:
                raise PipeOCRInputError(f"Document stuff '{self.document_stuff_name}' is not a PDF")
            ocr_output = await ocr_engine.extraction_from_pdf(
                pdf_path=document_path,
                pdf_url=url,
            )

        else:
            raise PipeOCRInputError("PipeOCR should have a non-None image_stuff_name or document_stuff_name")

        content: ListContent[PageContent] = ListContent(items=[])
        for _, page in ocr_output.pages.items():
            page_screenshot = await self.get_page_screenshot()
            content.items.append(
                PageContent(
                    text=TextContent(text=page.text),
                    images=[ImageContent(url=image.uri) for image in page.images],
                    screenshot=page_screenshot,
                )
            )

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

    async def get_page_screenshot(
        self,
    ) -> ImageContent:
        return ImageContent(url="page_screenhot.png")
