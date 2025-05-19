# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.


import pytest

from pipelex import pretty_print
from pipelex.core.domain import SpecialDomain
from pipelex.core.stuff_content import PageContent
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.pipe_operators.pipe_ocr import PipeOCR, PipeOCROutput
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from pipelex.pipe_works.pipe_router_protocol import PipeRouterProtocol
from tests.pipelex.test_data import PipeOCRTestCases


@pytest.mark.ocr
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeOCR:
    @pytest.mark.parametrize("image_url", PipeOCRTestCases.PIPE_OCR_IMAGE_TEST_CASES)
    async def test_pipe_ocr_image(
        self,
        pipe_router: PipeRouterProtocol,
        image_url: str,
    ):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOCR(
                code="adhoc_for_test_pipe_ocr_image",
                domain="generic",
                image_stuff_name="page_scan",
                should_add_screenshots=True,
                should_caption_images=False,
                output_concept_code=f"{SpecialDomain.NATIVE}.TextAndImage",
            ),
            working_memory=WorkingMemoryFactory.make_from_image(
                image_url=image_url,
                concept_code="ocr.PageScan",
                name="page_scan",
            ),
        )
        pipe_ocr_output: PipeOCROutput = await pipe_router.run_pipe_job(
            pipe_job=pipe_job,
        )
        ocr_text = pipe_ocr_output.main_stuff_as_list(item_type=PageContent)
        pretty_print(ocr_text, title="ocr_text")

    @pytest.mark.parametrize("pdf_url", PipeOCRTestCases.PIPE_OCR_PDF_TEST_CASES)
    async def test_pipe_ocr_pdf(
        self,
        pipe_router: PipeRouterProtocol,
        pdf_url: str,
    ):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOCR(
                code="adhoc_for_test_pipe_ocr_pdf",
                domain="generic",
                pdf_stuff_name="pdf",
                should_add_screenshots=True,
                should_caption_images=False,
                output_concept_code=f"{SpecialDomain.NATIVE}.TextAndImage",
            ),
            working_memory=WorkingMemoryFactory.make_from_pdf(
                pdf_url=pdf_url,
                concept_code=f"{SpecialDomain.NATIVE}.PDF",
                name="pdf",
            ),
        )
        pipe_ocr_output: PipeOCROutput = await pipe_router.run_pipe_job(
            pipe_job=pipe_job,
        )
        ocr_text = pipe_ocr_output.main_stuff_as_list(item_type=PageContent)
        pretty_print(ocr_text, title="ocr_text")
