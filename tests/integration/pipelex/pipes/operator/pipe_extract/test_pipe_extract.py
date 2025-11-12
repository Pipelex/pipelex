import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.page_content import PageContent
from pipelex.hub import get_concept_library, get_pipe_router
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint
from pipelex.pipe_operators.extract.pipe_extract_factory import PipeExtractFactory
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from tests.integration.pipelex.test_data import PipeExtractTestCases


@pytest.mark.dry_runnable
@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeExtract:
    @pytest.fixture(scope="class", autouse=True)
    def setup(self):
        concept_library = get_concept_library()
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="PageScan",
            domain="extract",
            blueprint=ConceptBlueprint(description="Lorem Ipsum"),
            concept_codes_from_the_same_domain=["PageScan"],
        )
        concept_library.add_new_concept(concept=concept_1)

        yield

        concept_library.teardown()

    @pytest.mark.usefixtures("setup")
    @pytest.mark.parametrize("image_url", PipeExtractTestCases.PIPE_OCR_IMAGE_TEST_CASES)
    async def test_pipe_extract_image(
        self,
        extract_choice_for_image: str,
        pipe_run_mode: PipeRunMode,
        image_url: str,
    ):
        pipe_extract_blueprint = PipeExtractBlueprint(
            description="OCR test for image processing",
            inputs={"page_scan": NativeConceptCode.IMAGE},
            output=NativeConceptCode.TEXT_AND_IMAGES,
            page_images=True,
            page_image_captions=False,
            page_views=True,
            page_views_dpi=72,
            model=extract_choice_for_image,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeExtractFactory.make_from_blueprint(
                domain="generic",
                pipe_code="adhoc_for_test_pipe_extract_from_image",
                blueprint=pipe_extract_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=WorkingMemoryFactory.make_from_image(
                image_url=image_url,
                name="page_scan",
            ),
        )
        pipe_extract_output = await get_pipe_router().run(
            pipe_job=pipe_job,
        )

        list_result = pipe_extract_output.main_stuff_as_list(item_type=PageContent)
        pretty_print(list_result, title="list_result")

    @pytest.mark.parametrize("pdf_url", PipeExtractTestCases.PIPE_OCR_PDF_TEST_CASES)
    @pytest.mark.parametrize("page_image_captions", [False])  # TODO: add True when captioning is implemented
    async def test_pipe_extract_from_pdf(
        self,
        extract_choice_for_pdf: str,
        pipe_run_mode: PipeRunMode,
        pdf_url: str,
        page_image_captions: bool,
    ):
        input_name = "arbitrary_name"
        blueprint = PipeExtractBlueprint(
            description="OCR test for PDF processing",
            inputs={input_name: NativeConceptCode.PDF},
            output=NativeConceptCode.TEXT_AND_IMAGES,
            model=extract_choice_for_pdf,
            page_images=True,
            page_image_captions=page_image_captions,
            page_views=True,
            page_views_dpi=72,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeExtractFactory.make_from_blueprint(
                domain="generic",
                pipe_code="adhoc_for_test_pipe_extract_from_pdf",
                blueprint=blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            working_memory=WorkingMemoryFactory.make_from_pdf(
                pdf_url=pdf_url,
                name=input_name,
            ),
        )
        pipe_extract_output = await get_pipe_router().run(
            pipe_job=pipe_job,
        )
        extracted_text = pipe_extract_output.main_stuff_as_list(item_type=PageContent)
        pretty_print(extracted_text, title="extracted_text")
