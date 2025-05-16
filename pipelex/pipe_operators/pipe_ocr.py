# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import List, Optional

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
    pdf_stuff_name: Optional[str] = None
    ocr_engine_name: Optional[str] = None

    @model_validator(mode="after")
    def validate_at_least_one_stuff_name(self) -> Self:
        if self.image_stuff_name is None and self.pdf_stuff_name is None:
            raise PipeOCRInputError("At least one of 'image_stuff_name' or 'pdf_stuff_name' must be provided")
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
            image_stuff = working_memory.get_stuff_as_image(name=self.image_stuff_name)
            image_path, url = clarify_path_or_url(path_or_url=image_stuff.url)
            ocr_output = await ocr_engine.extraction_from_image(
                image_path=image_path,
                image_url=url,
            )

        elif self.pdf_stuff_name:
            pdf_stuff = working_memory.get_stuff_as_pdf(name=self.pdf_stuff_name)
            pdf_path, url = clarify_path_or_url(path_or_url=pdf_stuff.url)  # pyright: ignore
            ocr_output = await ocr_engine.extraction_from_pdf(
                pdf_path=pdf_path,
                pdf_url=url,
            )

        else:
            raise PipeOCRInputError("PipeOCR should have a non-None image_stuff_name or pdf_stuff_name")

        # Build the output stuff, which is a list of page contents
        page_contents: List[PageContent] = []
        for _, page in ocr_output.pages.items():
            page_contents.append(
                PageContent(
                    text_and_image_content=TextAndImageContent(
                        text=TextContent(text=page.text) if page.text else None,
                        images=[ImageContent(url=image.uri) for image in page.images],
                    ),
                    screenshot=ImageContent(url=page.screenshot.uri) if page.screenshot else None,
                )
            )

        content = ListContent(items=page_contents)

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
