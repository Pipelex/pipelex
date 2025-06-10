import pytest

from pipelex import pretty_print
from pipelex.core.concept_native import NativeConcept
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.core.pipe_run_params import PipeRunMode
from pipelex.core.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuff_content import PageContent
from pipelex.core.working_memory_factory import WorkingMemoryFactory
from pipelex.hub import get_pipe_router
from pipelex.pipe_operators.pipe_ocr import PipeOcr, PipeOcrOutput
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from tests.pipelex.test_data import PipeOcrTestCases


@pytest.mark.dry_runnable
@pytest.mark.ocr
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeOCR:
    @pytest.mark.parametrize("image_url", PipeOcrTestCases.PIPE_OCR_IMAGE_TEST_CASES)
    async def test_pipe_ocr_image(
        self,
        pipe_run_mode: PipeRunMode,
        image_url: str,
    ):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOcr(
                code="adhoc_for_test_pipe_ocr_image",
                domain="generic",
                inputs=PipeInputSpec(
                    root={
                        "page_scan": "native.Image",
                    }
                ),
                should_include_images=True,
                should_caption_images=False,
                should_include_page_views=True,
                page_views_dpi=300,
                output_concept_code=NativeConcept.TEXT_AND_IMAGES.code,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
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
        pipe_run_mode: PipeRunMode,
        pdf_url: str,
    ):
        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOcr(
                code="adhoc_for_test_pipe_ocr_pdf",
                domain="generic",
                inputs=PipeInputSpec(
                    root={
                        "pdf": "native.PDF",
                    }
                ),
                should_include_images=True,
                should_caption_images=False,
                should_include_page_views=True,
                page_views_dpi=300,
                output_concept_code=NativeConcept.TEXT_AND_IMAGES.code,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
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
