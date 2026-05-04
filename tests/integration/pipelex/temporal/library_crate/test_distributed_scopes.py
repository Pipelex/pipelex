"""Two scoped workers on the same task queue: router (workflow-only) + runner (activity-only).

Validates that the worker scopes mechanism resolves correctly and that two scoped
workers can coexist on the same task queue (Temporal SDK rejects overlapping task
types — workflow-only + activity-only is the only viable split on one queue).

NOTE: this in-process test cannot reproduce the cross-process registry-propagation
bug described in TODOS.md, because both workers share the same Python process and
the same global `KajsonManager`. The deterministic cross-process regression lives
in the `/temporal-e2e-validate` skill, which spawns separate worker processes via
the `--scope router`/`--scope runner` CLI flags.
"""

import uuid
from collections.abc import Generator

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.test_data import DeferredHydrationTestData


@pytest.fixture(scope="class")
def pipe_job_with_dynamic_concept(is_class_registry_isolated: bool) -> Generator[PipeJob, None, None]:
    yield from pipe_job_from_bundle(
        bundle_file=DeferredHydrationTestData.BUNDLE_FILE,
        pipe_code=DeferredHydrationTestData.PIPE_CODE,
        isolated_registry=is_class_registry_isolated,
    )


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestDistributedScopes:
    async def test_dynamic_concept_across_router_and_runner_workers(
        self,
        pipe_job_with_dynamic_concept: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Two scoped workers on the same queue: WfPipeRun must land on a different
        worker than WfPipeRouter. Dynamic concept must still resolve end-to-end.
        """
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        worker_scopes = get_config().temporal.worker_scopes
        router_scope = worker_scopes.scopes["router"]
        runner_scope = worker_scopes.scopes["runner"]

        async with (
            get_task_manager().make_worker(
                temporal_client,
                task_queue=task_queue,
                is_not_sandboxed=True,
                scope=router_scope,
            ),
            get_task_manager().make_worker(
                temporal_client,
                task_queue=task_queue,
                is_not_sandboxed=True,
                scope=runner_scope,
            ),
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRouter.run,
                arg=pipe_job_with_dynamic_concept,
                id=workflow_id,
                task_queue=task_queue,
            )

        assert isinstance(pipe_output, PipeOutput)
        rehydrate_pipe_output(pipe_output, pipe_job=pipe_job_with_dynamic_concept)
        working_memory = pipe_output.working_memory
        assert working_memory is not None

        greeting_stuff = working_memory.get_stuff("greeting_result")
        assert isinstance(greeting_stuff.content, StructuredContent)
        assert hasattr(greeting_stuff.content, "message")
        assert hasattr(greeting_stuff.content, "language")
