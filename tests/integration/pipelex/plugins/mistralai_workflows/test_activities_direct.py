"""Layer-2 integration test: ``pipelex_run_pipe`` activity end-to-end.

Spins an in-process Temporal test environment plus a Mistral test worker,
and runs a workflow that invokes ``pipelex_run_pipe`` against a real loaded
Pipelex pipe. Skipped when ``mistralai-workflows`` is not installed.
"""

from typing import Any

import pytest
import pytest_asyncio

mistralai_workflows = pytest.importorskip("mistralai.workflows")

from mistralai.workflows.core.config.config import config as mistralai_config  # noqa: E402
from mistralai.workflows.testing import create_test_worker  # noqa: E402  # pyright: ignore[reportUnknownVariableType]
from temporalio.common import SearchAttributeKey  # noqa: E402
from temporalio.testing import WorkflowEnvironment  # noqa: E402

# Pipelex imports must be wrapped in ``imports_passed_through`` because the
# workflow sandbox would otherwise reject our pipelex imports while validating
# the workflow class. Activities themselves run outside the sandbox so the
# wrapped imports are only needed where the workflow body references them.
with mistralai_workflows.workflow.unsafe.imports_passed_through():
    from pipelex.plugins.mistralai_workflows.activities import pipelex_run_pipe
    from pipelex.plugins.mistralai_workflows.bridge import (
        PipelexPipeRunInput,
        PipelexPipeRunOutput,
    )
    from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode

PIPE_REF = "mistralai_workflows_bridge_test.bridge_func_pipe"
TEST_TASK_QUEUE = "pipelex-mistralai-workflows-test"


@mistralai_workflows.workflow.define(
    name="pipelex-bridge-test-workflow",
    enforce_determinism=False,  # bypass workflow sandbox for the integration test
)
class PipelexBridgeTestWorkflow:
    @mistralai_workflows.workflow.entrypoint
    async def run(self, payload_dict: dict[str, Any]) -> PipelexPipeRunOutput:
        payload = PipelexPipeRunInput.model_validate(payload_dict)
        output: PipelexPipeRunOutput = await pipelex_run_pipe(payload)
        return output


@pytest.fixture(scope="module", autouse=True)
def override_mistralai_task_queue():  # pyright: ignore[reportUnusedFunction]
    """Pin Mistral's global task_queue config to our test queue.

    Mistral's ``@activity`` wrapper dispatches via
    ``temporalio.workflow.execute_activity(..., task_queue=config.get_effective_task_queue())``,
    which reads the global ``mistralai_config.temporal.task_queue`` (default
    ``"default"``). If we don't override it, activities are scheduled on
    ``"default"`` while the worker polls ``TEST_TASK_QUEUE`` — the activity
    never gets picked up and the workflow hangs.
    """
    original = mistralai_config.temporal.task_queue
    mistralai_config.temporal.task_queue = TEST_TASK_QUEUE
    try:
        yield
    finally:
        mistralai_config.temporal.task_queue = original


@pytest_asyncio.fixture(scope="module")  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def workflow_env():
    # Mistral's workflow.define wraps the run method with code that upserts an
    # ``OtelTraceId`` search attribute on every workflow run. The dev server
    # rejects the workflow activation if the attribute isn't pre-registered on
    # the namespace, so we declare it here.
    env = await WorkflowEnvironment.start_local(  # pyright: ignore[reportUnknownMemberType]
        search_attributes=[SearchAttributeKey.for_keyword("OtelTraceId")],
    )
    try:
        yield env
    finally:
        await env.shutdown()


@pytest.mark.asyncio(loop_scope="class")
class TestPipelexRunPipeActivity:
    async def test_workflow_invokes_pipe_via_bridge_in_direct_mode(
        self,
        workflow_env: WorkflowEnvironment,
        bridge_test_library: str,  # noqa: ARG002
    ) -> None:
        payload = PipelexPipeRunInput(
            pipe_code=PIPE_REF,
            inputs={"input_text": "via mistralai workflow"},
            execution_mode=PipelexExecutionMode.DIRECT,
        )

        async with create_test_worker(
            workflow_env,
            workflows=[PipelexBridgeTestWorkflow],
            activities=[pipelex_run_pipe],
            task_queue=TEST_TASK_QUEUE,
        ):
            result_dict = await workflow_env.client.execute_workflow(
                PipelexBridgeTestWorkflow.run,
                {"payload_dict": payload.model_dump(mode="json")},
                id="pipelex-bridge-test-workflow-direct",
                task_queue=TEST_TASK_QUEUE,
            )

        result = PipelexPipeRunOutput.model_validate(result_dict)
        assert result.is_completed is True
        assert result.workflow_id is None
        assert result.main_stuff_name is not None
        assert result.output_dict["root"][result.main_stuff_name]["content"]["text"] == "via mistralai workflow"
