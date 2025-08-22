from typing import Any

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_input_spec import InputRequirementBlueprint
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_content import PageContent
from pipelex.hub import get_concept_provider, get_pipe_router
from pipelex.pipe_operators.pipe_ocr import PIPE_OCR_INPUT_NAME, PipeOcrOutput
from pipelex.pipe_operators.pipe_ocr_factory import PipeOcrBlueprint, PipeOcrFactory
from pipelex.pipe_works.pipe_job_factory import PipeJobFactory
from tests.integration.pipelex.test_data import PipeOcrTestCases


@pytest.mark.dry_runnable
@pytest.mark.ocr
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeOCR:
    @pytest.fixture(scope="class", autouse=True)
    def setup(self):
        concept_provider = get_concept_provider()
        concept_1 = ConceptFactory.make_from_blueprint(concept_code="PageScan", domain="ocr", blueprint=ConceptBlueprint(definition="Lorem Ipsum"))
        concept_provider.add_new_concept(concept=concept_1)

        yield

        concept_provider.teardown()

    @pytest.mark.parametrize("image_url", PipeOcrTestCases.PIPE_OCR_IMAGE_TEST_CASES)
    async def test_pipe_ocr_image(
        self,
        pipe_run_mode: PipeRunMode,
        image_url: str,
        setup: Any,
    ):
        concept_1 = get_concept_provider().get_required_concept(concept_string="ocr.PageScan")
        pipe_ocr_blueprint = PipeOcrBlueprint(
            definition="OCR test for image processing",
            inputs={"page_scan": InputRequirementBlueprint(concept_code=NativeConceptEnum.IMAGE.value)},
            output=NativeConceptEnum.TEXT_AND_IMAGES.value,
            page_images=True,
            page_image_captions=False,
            page_views=True,
            page_views_dpi=72,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOcrFactory.make_from_blueprint(
                domain="generic",
                pipe_code="adhoc_for_test_pipe_ocr_image",
                pipe_blueprint=pipe_ocr_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=WorkingMemoryFactory.make_from_image(
                image_url=image_url,
                concept_code=concept_1.concept_string,
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
        pipe_ocr_blueprint = PipeOcrBlueprint(
            definition="OCR test for PDF processing",
            inputs={PIPE_OCR_INPUT_NAME: InputRequirementBlueprint(concept_code=NativeConceptEnum.PDF.value)},
            output=NativeConceptEnum.TEXT_AND_IMAGES.value,
            page_images=True,
            page_image_captions=False,
            page_views=True,
            page_views_dpi=72,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOcrFactory.make_from_blueprint(
                domain="generic",
                pipe_code="adhoc_for_test_pipe_ocr_pdf",
                pipe_blueprint=pipe_ocr_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=WorkingMemoryFactory.make_from_pdf(
                pdf_url=pdf_url,
                concept_code=NativeConceptEnum.PDF.value,
                name=PIPE_OCR_INPUT_NAME,
            ),
        )
        pipe_ocr_output: PipeOcrOutput = await get_pipe_router().run_pipe_job(
            pipe_job=pipe_job,
        )
        ocr_text = pipe_ocr_output.main_stuff_as_list(item_type=PageContent)
        pretty_print(ocr_text, title="ocr_text")
