# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from typing_extensions import override

from pipelex.cogt.ocr.ocr_engine_abstract import OCREngineAbstract
from pipelex.cogt.ocr.ocr_engine_factory import OCREngineFactory
from pipelex.core.pipe import PipeAbstract, update_job_metadata_for_pipe
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff_content import TextAndImageContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.job_metadata import JobMetadata
from pipelex.tools.utils.path_utils import clarify_path_or_url


class PipeOCROutput(PipeOutput):
    pass


class PipeOCR(PipeAbstract):
    image_stuff_name: str
    ocr_engine_name: Optional[str] = None

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
        if not self.output_concept_code:
            raise ValueError("PipeOCR should have a non-None output_concept_code")
        image_stuff = working_memory.get_stuff(name=self.image_stuff_name)
        image_url = image_stuff.as_image.url

        image_path, url = clarify_path_or_url(path_or_url=image_url)  # pyright: ignore
        if not image_stuff.is_image:
            raise ValueError(f"Image stuff '{self.image_stuff_name}' is not an image")
        ocr_engine: OCREngineAbstract = OCREngineFactory.make_ocr_engine()

        ocr_output = await ocr_engine.extract_text_from_image(
            image_path=image_path,
            image_url=url,
        )

        ocr_output_text = ocr_output.text

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept_code=self.output_concept_code,
            content=TextAndImageContent(
                text=TextContent(text=ocr_output_text),
                image=[],
            ),
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        pipe_output = PipeOCROutput(
            working_memory=working_memory,
        )
        return pipe_output
