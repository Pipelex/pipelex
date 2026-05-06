"""Layer-2 integration test: ``pipelex_run_pipe_offloaded`` activity end-to-end.

Verifies that the ``OffloadableField``-based variant correctly wraps and
unwraps Pipelex payloads through a Mistral Workflows activity. Skipped when
``mistralai-workflows`` is not installed.

This test does NOT exercise Mistral's actual blob-storage offloading path —
that requires worker-level interceptor configuration with real S3/GCS/Azure
storage. It exercises the wrapping/unwrapping shape (the part Pipelex owns)
so users can confidently configure the offloading interceptor on their own
workers without surprises at the model boundary.
"""

from typing import Any

import pytest
import pytest_asyncio

mistralai_workflows = pytest.importorskip("mistralai.workflows")

from mistralai.workflows.core.config.config import config as mistralai_config  # noqa: E402
from mistralai.workflows.core.encoding.fields_offloader import OffloadableField  # noqa: E402
from mistralai.workflows.testing import create_test_worker  # noqa: E402  # pyright: ignore[reportUnknownVariableType]
from temporalio.common import SearchAttributeKey  # noqa: E402
from temporalio.testing import WorkflowEnvironment  # noqa: E402

with mistralai_workflows.workflow.unsafe.imports_passed_through():
    from pipelex.plugins.mistralai_workflows.activities import (
        PipelexPipeRunInputOffloaded,
        PipelexPipeRunOutputOffloaded,
        pipelex_run_pipe_offloaded,
    )
    from pipelex.plugins.mistralai_workflows.bridge import (
        PipelexPipeRunInput,
        PipelexPipeRunOutput,
    )
    from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode

PIPE_REF = "mistralai_workflows_bridge_test.bridge_func_pipe"
TEST_TASK_QUEUE = "pipelex-mistralai-workflows-offloaded-test"

# Larger than Mistral's default offloading threshold (typically a few KiB),
# small enough that the in-process Temporal test server still accepts it
# inline. Keeps the test self-contained while exercising a non-trivial
# payload through the OffloadableField wrapper.
LARGE_INPUT_SIZE_BYTES = 200 * 1024


@mistralai_workflows.workflow.define(
    name="pipelex-bridge-offloaded-test-workflow",
    enforce_determinism=False,
)
class PipelexBridgeOffloadedTestWorkflow:
    @mistralai_workflows.workflow.entrypoint
    async def run(self, payload_dict: dict[str, Any]) -> PipelexPipeRunOutput:
        inner = PipelexPipeRunInput.model_validate(payload_dict)
        wrapped = PipelexPipeRunInputOffloaded(payload=OffloadableField(value=inner))
        result: PipelexPipeRunOutputOffloaded = await pipelex_run_pipe_offloaded(wrapped)
        unwrapped: PipelexPipeRunOutput = result.payload.get_value()
        return unwrapped


@pytest.fixture(scope="module", autouse=True)
def override_mistralai_task_queue():  # pyright: ignore[reportUnusedFunction]
    """Pin Mistral's global task_queue config to our test queue (see test_activities_direct.py)."""
    original = mistralai_config.temporal.task_queue
    mistralai_config.temporal.task_queue = TEST_TASK_QUEUE
    try:
        yield
    finally:
        mistralai_config.temporal.task_queue = original


@pytest_asyncio.fixture(scope="module")  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def workflow_env():
    env = await WorkflowEnvironment.start_local(  # pyright: ignore[reportUnknownMemberType]
        search_attributes=[SearchAttributeKey.for_keyword("OtelTraceId")],
    )
    try:
        yield env
    finally:
        await env.shutdown()


@pytest.mark.asyncio(loop_scope="class")
class TestPipelexRunPipeOffloadedActivity:
    async def test_offloaded_activity_round_trips_large_payload(
        self,
        workflow_env: WorkflowEnvironment,
        bridge_test_library: str,  # noqa: ARG002
    ) -> None:
        large_text = "x" * LARGE_INPUT_SIZE_BYTES
        payload = PipelexPipeRunInput(
            pipe_code=PIPE_REF,
            inputs={"input_text": large_text},
            execution_mode=PipelexExecutionMode.DIRECT,
        )

        async with create_test_worker(
            workflow_env,
            workflows=[PipelexBridgeOffloadedTestWorkflow],
            activities=[pipelex_run_pipe_offloaded],
            task_queue=TEST_TASK_QUEUE,
        ):
            result_dict = await workflow_env.client.execute_workflow(
                PipelexBridgeOffloadedTestWorkflow.run,
                {"payload_dict": payload.model_dump(mode="json")},
                id="pipelex-bridge-offloaded-test-workflow",
                task_queue=TEST_TASK_QUEUE,
            )

        result = PipelexPipeRunOutput.model_validate(result_dict)
        assert result.is_completed is True
        assert result.workflow_id is None
        assert result.main_stuff_name is not None
        echoed_text = result.output_dict["root"][result.main_stuff_name]["content"]["text"]
        assert echoed_text == large_text
