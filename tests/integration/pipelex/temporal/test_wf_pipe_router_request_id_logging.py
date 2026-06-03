"""Integration test: ``WfPipeRouter`` binds ``request_id`` from the dispatched
``PipeJob`` onto every workflow log record.

The per-invocation binding at ``WfPipeRouter.run`` (``WorkflowLog(request_id=
workflow_arg.job_metadata.request_id)``) can break — reverting to a module-level
singleton, wrong attribute path — without any other test failing. This regression
net pins the wiring end-to-end against a real Temporal worker.

Mirrors ``test_wf_pipe_run_request_id_logging.py`` but exercises ``WfPipeRouter``
directly: the LLM activity is mocked to fail so the workflow short-circuits past
real inference while still emitting the opening ``Workflow start`` debug record
that carries ``request_id``.
"""

import logging
import uuid
from collections.abc import Generator

import pytest
from pytest_mock import MockerFixture
from temporalio.client import Client as TemporalClient
from temporalio.client import WorkflowFailureError
from temporalio.common import RetryPolicy
from typing_extensions import override

from pipelex.config import get_config
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.wf_pipe_router import WfPipeRouter
from tests.integration.pipelex.error_handling.test_data import ErrorReportParityTestData
from tests.integration.pipelex.fixtures.pipe_job_helpers import pipe_job_from_bundle

_REQUEST_ID = "r-wf-pipe-router-logging-9c2b"
_ACT_LLM_GEN_TEXT_TARGET = "pipelex.temporal.tprl_content_generation.act_llm_generate.llm_gen_text"


@pytest.fixture(scope="class")
def request_id_router_job() -> Generator[PipeJob, None, None]:
    """A PipeJob whose ``job_metadata`` carries a known ``request_id``.

    LIVE mode is required so the workflow actually dispatches the LLM activity —
    DRY mode would short-circuit before the activity (and the mock) fires.
    """
    for pipe_job in pipe_job_from_bundle(
        bundle_file=ErrorReportParityTestData.BUNDLE_FILE,
        pipe_code=ErrorReportParityTestData.PIPE_CODE,
        pipe_run_mode=PipeRunMode.LIVE,
    ):
        yield pipe_job.model_copy(
            update={"job_metadata": pipe_job.job_metadata.model_copy(update={"request_id": _REQUEST_ID})},
        )


class _RecordingHandler(logging.Handler):
    """Captures every emitted ``LogRecord`` for post-run inspection."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeRouterRequestIdLogging:
    @pytest.fixture
    def temporal_enabled(self) -> Generator[None, None, None]:
        """Enable ``temporal.is_enabled`` for the test — the worker's LLM activity
        path checks this flag. Mirrors ``test_workflow_error_report_full_chain.py``.
        """
        config = get_config()
        previous = config.temporal.is_enabled
        config.temporal = config.temporal.model_copy(update={"is_enabled": True})
        yield
        config.temporal = config.temporal.model_copy(update={"is_enabled": previous})

    async def test_dispatched_request_id_rides_on_router_workflow_log_records(
        self,
        temporal_client: TemporalClient,
        mocker: MockerFixture,
        temporal_enabled: None,  # noqa: ARG002 - enables temporal.is_enabled for the duration
        request_id_router_job: PipeJob,
    ) -> None:
        # Make the LLM activity fail fast and non-retryably so WfPipeRouter
        # short-circuits past real inference. The opening ``Workflow start``
        # debug record (which we want to assert on) fires before any pipe work.
        mocker.patch(
            _ACT_LLM_GEN_TEXT_TARGET,
            new=mocker.AsyncMock(side_effect=ErrorReportParityTestData.make_failing_llm_error()),
        )

        task_queue = f"q_wfrouter_reqid_{uuid.uuid4().hex[:8]}"
        workflow_id = f"wf_router_reqid_{uuid.uuid4().hex[:8]}"

        # Capture records straight off the Temporal workflow logger: the
        # unsandboxed worker runs workflow code in-process, so its records reach
        # this process's ``temporalio.workflow`` logger. DEBUG level so the
        # opening ``Workflow start`` record (where request_id first binds) is
        # captured alongside the rest.
        temporal_workflow_logger = logging.getLogger("temporalio.workflow")
        handler = _RecordingHandler()
        original_level = temporal_workflow_logger.level
        try:
            temporal_workflow_logger.addHandler(handler)
            temporal_workflow_logger.setLevel(logging.DEBUG)
            # Use the production task manager's worker (registers WfPipeRouter
            # and the full activity catalog including ``act_llm_gen_text``) so
            # the mocked LLM call actually fires inside the activity. The
            # unsandboxed runner keeps workflow code in-process so the
            # workflow logger records reach this handler.
            async with get_task_manager().make_worker(
                temporal_client,
                task_queue=task_queue,
                is_not_sandboxed=True,
            ):
                with pytest.raises(WorkflowFailureError):
                    await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                        workflow=WfPipeRouter.run,
                        arg=request_id_router_job,
                        id=workflow_id,
                        task_queue=task_queue,
                        retry_policy=RetryPolicy(maximum_attempts=1),
                    )
        finally:
            temporal_workflow_logger.removeHandler(handler)
            temporal_workflow_logger.setLevel(original_level)

        records_with_request_id = [record for record in handler.records if getattr(record, "request_id", None) == _REQUEST_ID]
        assert records_with_request_id, (
            f"expected WfPipeRouter workflow log records carrying request_id={_REQUEST_ID!r}; "
            f"captured {len(handler.records)} record(s), request_ids seen: "
            f"{sorted({str(getattr(record, 'request_id', None)) for record in handler.records})}"
        )
