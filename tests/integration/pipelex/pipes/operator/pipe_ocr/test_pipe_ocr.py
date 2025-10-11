import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_input_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.pipe_run_params import PipeRunMode
from pipelex.core.pipes.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.core.stuffs.stuff_content import PageContent
from pipelex.hub import get_concept_provider, get_pipe_router
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint
from pipelex.pipe_operators.ocr.pipe_ocr_factory import PipeOcrFactory
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
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="PageScan",
            domain="ocr",
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["PageScan"],
        )
        concept_provider.add_new_concept(concept=concept_1)

        yield

        concept_provider.teardown()

    @pytest.mark.usefixtures("setup")
    @pytest.mark.parametrize("image_url", PipeOcrTestCases.PIPE_OCR_IMAGE_TEST_CASES)
    async def test_pipe_ocr_image(
        self,
        ocr_choice_for_image: str,
        pipe_run_mode: PipeRunMode,
        image_url: str,
    ):
        pipe_ocr_blueprint = PipeOcrBlueprint(
            description="OCR test for image processing",
            inputs={"page_scan": InputRequirementBlueprint(concept=NativeConceptEnum.IMAGE)},
            output=NativeConceptEnum.TEXT_AND_IMAGES,
            page_images=True,
            page_image_captions=False,
            page_views=True,
            page_views_dpi=72,
            ocr=ocr_choice_for_image,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOcrFactory.make_from_blueprint(
                domain="generic",
                pipe_code="adhoc_for_test_pipe_ocr_image",
                blueprint=pipe_ocr_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=WorkingMemoryFactory.make_from_image(
                image_url=image_url,
                name="page_scan",
            ),
        )
        pipe_ocr_output = await get_pipe_router().run(
            pipe_job=pipe_job,
        )

        ocr_text = pipe_ocr_output.main_stuff_as_list(item_type=PageContent)
        pretty_print(ocr_text, title="ocr_text")

    @pytest.mark.parametrize("pdf_url", PipeOcrTestCases.PIPE_OCR_PDF_TEST_CASES)
    async def test_pipe_ocr_pdf(
        self,
        ocr_choice_for_pdf: str,
        pipe_run_mode: PipeRunMode,
        pdf_url: str,
    ):
        input_name = "arbitrary_name"
        pipe_ocr_blueprint = PipeOcrBlueprint(
            description="OCR test for PDF processing",
            inputs={input_name: InputRequirementBlueprint(concept=NativeConceptEnum.PDF)},
            output=NativeConceptEnum.TEXT_AND_IMAGES,
            ocr=ocr_choice_for_pdf,
            page_images=True,
            page_image_captions=False,
            page_views=True,
            page_views_dpi=72,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeOcrFactory.make_from_blueprint(
                domain="generic",
                pipe_code="adhoc_for_test_pipe_ocr_pdf",
                blueprint=pipe_ocr_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=WorkingMemoryFactory.make_from_pdf(
                pdf_url=pdf_url,
                name=input_name,
            ),
        )
        pipe_ocr_output = await get_pipe_router().run(
            pipe_job=pipe_job,
        )
        ocr_text = pipe_ocr_output.main_stuff_as_list(item_type=PageContent)
        pretty_print(ocr_text, title="ocr_text")
