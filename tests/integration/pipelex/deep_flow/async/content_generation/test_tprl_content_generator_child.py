import pytest
from temporalio.client import Client as TemporalClient

from pipelex import log
from pipelex.config import get_config
from pipelex.deep_flow.temporal_manager import get_temporal_manager
from pipelex.deep_flow.test_extras.wf_test_content_generator_child import WfTestContentGeneratorChild


@pytest.mark.gha_disabled  # because it needs an external worker
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestTprlContentGeneratorChild:
    async def test_tprl_content_generator_child(self, temporal_client: TemporalClient):
        task_queue_name = get_config().deep_flow.worker_config.task_queue
        workflow_id = get_temporal_manager().make_top_workflow_id(base_id="test_child_craft")
        log.debug(f"Top workflow_id (UT): {workflow_id}")
        await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
            workflow=WfTestContentGeneratorChild.run,
            id=workflow_id,
            task_queue=task_queue_name,
        )
