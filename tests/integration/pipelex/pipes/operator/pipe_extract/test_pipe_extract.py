from typing import Callable

import pytest

from pipelex import pretty_print
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_concept_library, get_pipe_router
from pipelex.pipe_operators.extract.pipe_extract import PipeExtract
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.job_metadata import JobMetadata
from tests.integration.pipelex.test_data import PipeExtractTestCases


@pytest.mark.dry_runnable
@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.asyncio(loop_scope="class")
class TestPipeExtract:
    @pytest.fixture(scope="class", autouse=True)
    def setup(self, load_empty_library: Callable[[], None]):
        load_empty_library()
        concept_library = get_concept_library()
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="PageScan",
            domain_code="extract",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum"),
        )
        concept_library.add_new_concept(concept=concept_1)

        yield

        concept_library.teardown()

    @pytest.mark.usefixtures("setup")
    @pytest.mark.parametrize("image_url", PipeExtractTestCases.PIPE_OCR_IMAGE_TEST_CASES)
    async def test_pipe_extract_image(
        self,
        job_metadata: JobMetadata,
        extract_choice_for_image: str,
        pipe_run_mode: PipeRunMode,
        image_url: str,
    ):
        pipe_extract_blueprint = PipeExtractBlueprint(
            description="OCR test for image processing",
            inputs={"page_scan": NativeConceptCode.IMAGE},
            output="Page[]",
            max_page_images=None,
            page_image_captions=False,
            page_views=True,
            page_views_dpi=72,
            model=extract_choice_for_image,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeFactory[PipeExtract].make_from_blueprint(
                domain_code="generic",
                pipe_code="adhoc_for_test_pipe_extract_from_image",
                blueprint=pipe_extract_blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=WorkingMemoryFactory.make_from_single_stuff(
                stuff=StuffFactory.make_stuff(
                    concept=ConceptFactory.make(
                        concept_code="PageScan",
                        domain_code="extract",
                        description="Lorem Ipsum",
                        structure_class_name="PageScan",
                    ),
                    content=ImageContent(url=image_url),
                    name="page_scan",
                ),
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
        job_metadata: JobMetadata,
        extract_choice_for_pdf: str,
        pipe_run_mode: PipeRunMode,
        pdf_url: str,
        page_image_captions: bool,
    ):
        input_name = "arbitrary_name"
        blueprint = PipeExtractBlueprint(
            description="OCR test for PDF processing",
            inputs={input_name: NativeConceptCode.DOCUMENT},
            output="Page[]",
            model=extract_choice_for_pdf,
            max_page_images=None,
            page_image_captions=page_image_captions,
            page_views=True,
            page_views_dpi=72,
        )

        pipe_job = PipeJobFactory.make_pipe_job(
            pipe=PipeFactory[PipeExtract].make_from_blueprint(
                domain_code="generic",
                pipe_code="adhoc_for_test_pipe_extract_from_pdf",
                blueprint=blueprint,
            ),
            pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=pipe_run_mode),
            job_metadata=job_metadata,
            working_memory=WorkingMemoryFactory.make_from_single_stuff(
                stuff=StuffFactory.make_stuff(
                    concept=ConceptFactory.make_native_concept(
                        native_concept_code=NativeConceptCode.DOCUMENT,
                    ),
                    content=DocumentContent(url=pdf_url),
                    name=input_name,
                ),
            ),
        )
        pipe_extract_output = await get_pipe_router().run(
            pipe_job=pipe_job,
        )
        extracted_pages = pipe_extract_output.main_stuff_as_list(item_type=PageContent)
        pretty_print(extracted_pages, title="Extracted pages")
