import uuid

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.test_extras.temporal_test_tasks import TEMPORAL_TEST_ACTIVITIES, TEMPORAL_TEST_WORKFLOWS
from pipelex.temporal.test_extras.wf_test_content_generator_child import WfTestContentGeneratorChild


@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestTprlContentGeneratorChild:
    async def test_tprl_content_generator_child(self, temporal_client: TemporalClient, tprl_job_metadata: JobMetadata):
        task_queue = str(uuid.uuid4())
        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
            test_workflows=TEMPORAL_TEST_WORKFLOWS,
            test_activities=TEMPORAL_TEST_ACTIVITIES,
        ):
            await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfTestContentGeneratorChild.run,
                id=tprl_job_metadata.pipeline_run_id,
                task_queue=task_queue,
            )
