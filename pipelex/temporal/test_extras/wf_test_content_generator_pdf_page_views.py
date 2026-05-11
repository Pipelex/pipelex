from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from pipelex import pretty_print
    from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
    from pipelex.cogt.content_generation.content_generator_protocol import ContentGeneratorProtocol  # noqa: TC001
    from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
    from pipelex.cogt.extract.extract_input import ExtractInput
    from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
    from pipelex.pipeline.job_metadata import JobMetadata
    from pipelex.temporal.exceptions import ContentGenerationError
    from pipelex.temporal.log_temporal import workflow_log
    from pipelex.temporal.tprl_content_generation.content_generator_in_workflow_factory import ContentGeneratorInWorkflowFactory
    from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
    from tests.integration.pipelex.temporal.test_data import PipeTestCases


@workflow.defn(name="wf_test_content_generator_pdf_page_views")
class WfTestContentGeneratorPdfPageViews:
    """Exercise the ``document_uri`` + ``should_include_page_views=True`` branch of
    ``ContentGeneratorInWorkflow.make_extract_pages`` end-to-end.

    Validates the wiring that unit tests can only mock: a real PDF is dispatched to
    ``act_extract_gen_extract_pages`` for OCR AND to ``act_render_page_views`` for
    pypdfium2 rendering, then the in-workflow attachment loop pairs each rendered
    page image with its corresponding ``PageContent.page_view``.
    """

    @workflow.run
    async def run(self, is_dry_run: bool = False) -> None:
        workflow_log.debug("Workflow start")
        content_generator: ContentGeneratorProtocol
        if is_dry_run:
            content_generator = ContentGeneratorDry()
        else:
            generated_content_factory = GeneratedContentFactory(storage_provider=InMemoryStorageProvider())
            content_generator = ContentGeneratorInWorkflowFactory.make_content_generator_in_workflow(
                generated_content_factory=generated_content_factory,
            )

        job_metadata = JobMetadata(
            user_id="temporal-test",
            pipeline_run_id=workflow.info().workflow_id,
        )

        page_contents = await content_generator.make_extract_pages(
            extract_input=ExtractInput(
                document_uri=PipeTestCases.JOB_OFFER_PDF_LOCAL,
            ),
            extract_handle="azure-document-intelligence",
            job_metadata=job_metadata,
            extract_job_params=ExtractJobParams(
                max_nb_images=0,
                image_min_size=None,
                should_caption_images=False,
                should_include_page_views=True,
                page_views_dpi=72,
            ),
            extract_job_config=ExtractJobConfig(),
        )
        pretty_print(page_contents, title="make_extract_pages with page_views (document_uri)")

        if not page_contents:
            msg = "make_extract_pages returned no pages"
            raise ContentGenerationError(msg)
        for index_page, page_content in enumerate(page_contents):
            if page_content.page_view is None:
                msg = (
                    f"Page {index_page} has no page_view; the document_uri + should_include_page_views branch did not attach the rendered page image"
                )
                raise ContentGenerationError(msg)

        workflow_log.debug("Workflow complete")
