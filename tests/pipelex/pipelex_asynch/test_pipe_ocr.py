import pytest

from pipelex import pretty_print
from pipelex.core.concept_native import NativeConcept
from pipelex.core.stuff_content import PageContent
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_pipe_router
from pipelex.pipe_operators.pipe_ocr import PipeOcr, PipeOcrOutput
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from tests.pipelex.test_data import PipeOcrTestCases


@pytest.mark.ocr
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeOCR:
    @pytest.mark.parametrize("image_url", PipeOcrTestCases.PIPE_OCR_IMAGE_TEST_CASES)
    async def test_pipe_ocr_image(
        self,
        image_url: str,
    ):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOcr(
                code="adhoc_for_test_pipe_ocr_image",
                domain="generic",
                image_stuff_name="page_scan",
                should_include_images=True,
                should_caption_images=False,
                should_include_page_views=True,
                page_views_dpi=300,
                output_concept_code=NativeConcept.TEXT_AND_IMAGES.code,
            ),
            working_memory=WorkingMemoryFactory.make_from_image(
                image_url=image_url,
                concept_code="ocr.PageScan",
                name="page_scan",
            ),
        )
        pipe_ocr_output: PipeOcrOutput = await get_pipe_router().run_pipe_job(
            pipe_job=pipe_job,
        )
        ocr_text = pipe_ocr_output.main_stuff_as_list(item_type=PageContent)
        pretty_print(ocr_text, title="ocr_text")

    @pytest.mark.parametrize("pdf_url", PipeOcrTestCases.PIPE_OCR_PDF_TEST_CASES)
    async def test_pipe_ocr_pdf(
        self,
        pdf_url: str,
    ):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOcr(
                code="adhoc_for_test_pipe_ocr_pdf",
                domain="generic",
                pdf_stuff_name="pdf",
                should_include_images=True,
                should_caption_images=False,
                should_include_page_views=True,
                page_views_dpi=300,
                output_concept_code=NativeConcept.TEXT_AND_IMAGES.code,
            ),
            working_memory=WorkingMemoryFactory.make_from_pdf(
                pdf_url=pdf_url,
                concept_code=NativeConcept.PDF.code,
                name="pdf",
            ),
        )
        pipe_ocr_output: PipeOcrOutput = await get_pipe_router().run_pipe_job(
            pipe_job=pipe_job,
        )
        ocr_text = pipe_ocr_output.main_stuff_as_list(item_type=PageContent)
        pretty_print(ocr_text, title="ocr_text")
