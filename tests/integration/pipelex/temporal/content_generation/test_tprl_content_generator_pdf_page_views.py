import uuid

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.test_extras.temporal_test_tasks import TEMPORAL_TEST_ACTIVITIES, TEMPORAL_TEST_WORKFLOWS
from pipelex.temporal.test_extras.wf_test_content_generator_pdf_page_views import WfTestContentGeneratorPdfPageViews


@pytest.mark.extract
@pytest.mark.inference
@pytest.mark.dry_runnable
@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestTprlContentGeneratorPdfPageViews:
    async def test_tprl_content_generator_pdf_page_views(
        self,
        temporal_client: TemporalClient,
        tprl_job_metadata: JobMetadata,
        pipe_run_mode: PipeRunMode,
    ):
        """End-to-end coverage for ContentGeneratorInWorkflow.make_extract_pages with
        document_uri + should_include_page_views=True.

        The unit suite mocks both activities; this test runs them for real (Azure
        Document Intelligence + pypdfium2 page rendering) through Temporal. Failure
        modes this catches that mocked unit tests cannot:
          - RenderPageViewsAssignment serialization mismatch across the activity boundary
          - page_views_dpi config plumbing dropped before the activity payload is built
          - The in-workflow page_view attachment loop running in the wrong order or
            on a stale page_contents reference
          - Activity registration miss for act_render_page_views in the test worker
        """
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
            test_workflows=TEMPORAL_TEST_WORKFLOWS,
            test_activities=TEMPORAL_TEST_ACTIVITIES,
        ):
            await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfTestContentGeneratorPdfPageViews.run,
                arg=pipe_run_mode.is_dry,
                id=tprl_job_metadata.pipeline_run_id,
                task_queue=task_queue,
            )
