"""Layer-2 integration test: ``pipelex_run_pipe_streaming`` activity end-to-end.

Spins an in-process Temporal test environment plus a Mistral test worker
configured with the ``EventInterceptor``, runs a workflow that invokes
``pipelex_run_pipe_streaming``, and asserts that the lifecycle events
(``CustomTaskStarted`` → ``CustomTaskInProgress`` → ``CustomTaskCompleted``)
were published with the expected ``custom_task_type`` and payload shape.

Skipped when ``mistralai-workflows`` is not installed.
"""

from typing import Any, cast

import pytest
import pytest_asyncio

mistralai_workflows = pytest.importorskip("mistralai.workflows")

from mistralai.workflows.core._events.event_context import EventContext  # noqa: E402, PLC2701
from mistralai.workflows.core.config.config import config as mistralai_config  # noqa: E402
from mistralai.workflows.protocol.v1.events import (  # noqa: E402
    CustomTaskCompleted,
    CustomTaskInProgress,
    CustomTaskStarted,
    WorkflowEvent,
)
from mistralai.workflows.testing import (  # noqa: E402
    create_capturing_mock_events_client,
    create_test_worker_with_events,  # pyright: ignore[reportUnknownVariableType]
)
from temporalio.common import SearchAttributeKey  # noqa: E402
from temporalio.testing import WorkflowEnvironment  # noqa: E402

with mistralai_workflows.workflow.unsafe.imports_passed_through():
    from pipelex.plugins.mistralai_workflows.bridge import (
        PipelexPipeRunInput,
        PipelexPipeRunOutput,
    )
    from pipelex.plugins.mistralai_workflows.execution_mode import PipelexExecutionMode
    from pipelex.plugins.mistralai_workflows.streaming import (
        PIPELEX_PIPE_RUN_TASK_TYPE,
        pipelex_run_pipe_streaming,
    )

PIPE_REF = "mistralai_workflows_bridge_test.bridge_func_pipe"
PIPE_REF_SEQUENCE = "mistralai_workflows_bridge_test.bridge_sequence_pipe"
TEST_TASK_QUEUE = "pipelex-mistralai-workflows-streaming-test"


@mistralai_workflows.workflow.define(
    name="pipelex-bridge-streaming-test-workflow",
    enforce_determinism=False,
)
class PipelexBridgeStreamingTestWorkflow:
    @mistralai_workflows.workflow.entrypoint
    async def run(self, payload_dict: dict[str, Any]) -> PipelexPipeRunOutput:
        payload = PipelexPipeRunInput.model_validate(payload_dict)
        output: PipelexPipeRunOutput = await pipelex_run_pipe_streaming(payload)
        return output


@pytest.fixture(scope="module", autouse=True)
def override_mistralai_task_queue():  # pyright: ignore[reportUnusedFunction]
    """Pin Mistral's global task_queue to our test queue (see test_activities_direct.py)."""
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
class TestPipelexRunPipeStreamingActivity:
    async def test_workflow_emits_custom_task_lifecycle_events(
        self,
        workflow_env: WorkflowEnvironment,
        bridge_test_library: str,  # noqa: ARG002
    ) -> None:
        captured_events: list[WorkflowEvent] = []
        mock_events_client = create_capturing_mock_events_client(captured_events)

        payload = PipelexPipeRunInput(
            pipe_code=PIPE_REF,
            inputs={"input_text": "via streaming activity"},
            execution_mode=PipelexExecutionMode.DIRECT,
        )

        async with (
            EventContext(events_client=mock_events_client),
            create_test_worker_with_events(
                workflow_env,
                workflows=[PipelexBridgeStreamingTestWorkflow],
                activities=[pipelex_run_pipe_streaming],
                task_queue=TEST_TASK_QUEUE,
            ),
        ):
            result_dict = await workflow_env.client.execute_workflow(
                PipelexBridgeStreamingTestWorkflow.run,
                {"payload_dict": payload.model_dump(mode="json")},
                id="pipelex-bridge-streaming-test-workflow",
                task_queue=TEST_TASK_QUEUE,
            )

        result = PipelexPipeRunOutput.model_validate(result_dict)
        assert result.is_completed is True
        assert result.main_stuff_name is not None
        assert result.output_dict["root"][result.main_stuff_name]["content"]["text"] == "via streaming activity"

        custom_task_events = [
            event
            for event in captured_events
            if isinstance(event, (CustomTaskStarted, CustomTaskInProgress, CustomTaskCompleted))
            and event.attributes.custom_task_type == PIPELEX_PIPE_RUN_TASK_TYPE
        ]

        # Expect exactly one Started, at least one InProgress (the "completed" state update),
        # and one Completed event for the pipe-run task.
        started_events = [event for event in custom_task_events if isinstance(event, CustomTaskStarted)]
        in_progress_events = [event for event in custom_task_events if isinstance(event, CustomTaskInProgress)]
        completed_events = [event for event in custom_task_events if isinstance(event, CustomTaskCompleted)]

        assert len(started_events) == 1, f"expected 1 CustomTaskStarted, got {len(started_events)}"
        assert len(in_progress_events) >= 1, f"expected >=1 CustomTaskInProgress, got {len(in_progress_events)}"
        assert len(completed_events) == 1, f"expected 1 CustomTaskCompleted, got {len(completed_events)}"

        started_payload = started_events[0].attributes.payload.value
        assert started_payload["pipe_code"] == PIPE_REF
        assert started_payload["phase"] == "started"
        assert started_payload["execution_mode"] == PipelexExecutionMode.DIRECT

        completed_payload = completed_events[0].attributes.payload.value
        assert completed_payload["phase"] == "completed"
        assert completed_payload["pipeline_run_id"] == result.pipeline_run_id
        assert completed_payload["main_stuff_name"] == result.main_stuff_name

    async def test_multistep_pipe_emits_per_step_events(
        self,
        workflow_env: WorkflowEnvironment,
        bridge_test_library: str,  # noqa: ARG002
    ) -> None:
        """A two-step PipeSequence produces one CustomTaskInProgress per pipe boundary."""
        captured_events: list[WorkflowEvent] = []
        mock_events_client = create_capturing_mock_events_client(captured_events)

        payload = PipelexPipeRunInput(
            pipe_code=PIPE_REF_SEQUENCE,
            inputs={"input_text": "step events"},
            execution_mode=PipelexExecutionMode.DIRECT,
        )

        async with (
            EventContext(events_client=mock_events_client),
            create_test_worker_with_events(
                workflow_env,
                workflows=[PipelexBridgeStreamingTestWorkflow],
                activities=[pipelex_run_pipe_streaming],
                task_queue=TEST_TASK_QUEUE,
            ),
        ):
            result_dict = await workflow_env.client.execute_workflow(
                PipelexBridgeStreamingTestWorkflow.run,
                {"payload_dict": payload.model_dump(mode="json")},
                id="pipelex-bridge-streaming-multistep-test-workflow",
                task_queue=TEST_TASK_QUEUE,
            )

        result = PipelexPipeRunOutput.model_validate(result_dict)
        assert result.is_completed is True
        assert result.main_stuff_name is not None
        # Both steps must have run in declaration order: upper("step events") wrapped with [STEP2:...]
        assert result.output_dict["root"][result.main_stuff_name]["content"]["text"] == "[STEP2:STEP EVENTS]"

        custom_task_events = [
            event
            for event in captured_events
            if isinstance(event, (CustomTaskStarted, CustomTaskInProgress, CustomTaskCompleted))
            and event.attributes.custom_task_type == PIPELEX_PIPE_RUN_TASK_TYPE
        ]
        started_events = [event for event in custom_task_events if isinstance(event, CustomTaskStarted)]
        in_progress_events = [event for event in custom_task_events if isinstance(event, CustomTaskInProgress)]
        completed_events = [event for event in custom_task_events if isinstance(event, CustomTaskCompleted)]

        assert len(started_events) == 1, f"expected 1 CustomTaskStarted, got {len(started_events)}"
        assert len(completed_events) == 1, f"expected 1 CustomTaskCompleted, got {len(completed_events)}"

        # CustomTaskInProgress carries a JSONPatchPayload — value is a list of JSON Patch operations
        # (one per field that *changed* between previous and new state). Flatten each event's patches
        # into a {field: value} dict.
        #
        # Important: a field only appears in the patch when its value actually changed. If two
        # consecutive update_state calls write the same value to a field (e.g. last_event_kind back
        # to "pipe_start" without a "pipe_end_success" in between), that field is absent from the
        # second patch. We therefore key on /started_steps (strictly monotonic on every pipe_start)
        # and /completed_steps (strictly monotonic on every pipe_end_success).
        patches_per_event = [_patches_to_changes(event) for event in in_progress_events]

        pipe_start_changes = [changes for changes in patches_per_event if "started_steps" in changes]
        pipe_end_success_changes = [changes for changes in patches_per_event if "completed_steps" in changes]
        assert len(pipe_start_changes) >= 3, f"expected >=3 pipe_start in_progress events, got {len(pipe_start_changes)}"
        assert len(pipe_end_success_changes) >= 3, f"expected >=3 pipe_end_success in_progress events, got {len(pipe_end_success_changes)}"

        # Order: outer PipeSequence first, then step_one, then step_two. /current_step_pipe_code
        # changes on every pipe_start (each pipe has a distinct code) so it always appears in the patch.
        step_codes_in_order = [changes["current_step_pipe_code"] for changes in pipe_start_changes]
        assert step_codes_in_order[0].endswith("bridge_sequence_pipe")
        assert step_codes_in_order[1].endswith("bridge_seq_step_one")
        assert step_codes_in_order[2].endswith("bridge_seq_step_two")

        # started_steps counter is monotonic 1, 2, 3 across the first three pipe_start events.
        started_steps_seq = [changes["started_steps"] for changes in pipe_start_changes[:3]]
        assert started_steps_seq == [1, 2, 3]

        # completed_steps reaches at least 3 by the end.
        max_completed = max(changes["completed_steps"] for changes in pipe_end_success_changes)
        assert max_completed >= 3

        # Phase 2.0 fields still surfaced on the final completed event (a JSONPayload — full state snapshot).
        completed_payload = completed_events[0].attributes.payload.value
        assert completed_payload["phase"] == "completed"
        assert completed_payload["pipeline_run_id"] == result.pipeline_run_id
        assert completed_payload["main_stuff_name"] == result.main_stuff_name


def _patches_to_changes(event: CustomTaskInProgress) -> dict[str, Any]:
    """Flatten a CustomTaskInProgress JSON Patch list into a {field: value} dict.

    Each ``update_state`` call produces a single ``CustomTaskInProgress`` with
    a list of root-level "add"/"replace" patches (paths look like ``/field``).
    Returns a dict of just the fields that changed in this event.
    """
    changes: dict[str, Any] = {}
    payload_value: Any = event.attributes.payload.value
    if not isinstance(payload_value, list):
        return changes
    raw_patches = cast("list[Any]", payload_value)
    for raw_patch in raw_patches:
        if isinstance(raw_patch, dict):
            patch_dict = cast("dict[str, Any]", raw_patch)
        else:
            patch_dict = cast("dict[str, Any]", raw_patch.model_dump())
        op = patch_dict.get("op")
        path = patch_dict.get("path", "")
        if op in {"add", "replace"} and isinstance(path, str) and path.startswith("/"):
            field = path[1:]
            if field:
                changes[field] = patch_dict.get("value")
    return changes
