# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.


import pytest

from pipelex import pretty_print
from pipelex.core.domain import SpecialDomain
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.pipe_operators.pipe_ocr import PipeOCR, PipeOCROutput
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
from tests.pipelex.test_data import PipeOCRTestCases


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeOCR:
    @pytest.mark.parametrize("image_file_path,", PipeOCRTestCases.PIPE_OCR_TEST_CASES)
    async def test_pipe_ocr(
        self,
        pipe_router: PipeRouterProtocol,
        image_file_path: str,
    ):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOCR(
                domain="generic",
                image_stuff_name="page_scan",
                output_concept_code=f"{SpecialDomain.NATIVE}.Text",
            ),
            working_memory=WorkingMemoryFactory.make_from_image(
                image_url=image_file_path,
                concept_code="ocr.PageScan",
                name="page_scan",
            ),
        )
        pipe_ocr_output: PipeOCROutput = await pipe_router.run_pipe_job(
            pipe_job=pipe_job,
        )
        ocr_text = pipe_ocr_output.main_stuff_as_text_and_image
        pretty_print(ocr_text, title="ocr_text")
