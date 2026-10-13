"""A router running each batch item as an execution of its own, as the engines Pipelex runs on do, and what it needs."""

from contextvars import ContextVar
from typing import TYPE_CHECKING

import kajson
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.text_content import TextContent
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.runtime_hub import get_event_log_override
from pipelex.system.job_metadata import JobMetadata

if TYPE_CHECKING:
    from pipelex.system.trace_context import TraceContext

# Set while an attempt the engine is about to lose runs: the attempt fails at the step that condenses its filing.
_IS_LOST_ATTEMPT: ContextVar[bool] = ContextVar("invocation_paths_is_lost_attempt", default=False)


def invocation_paths_condense_filing(working_memory: WorkingMemory) -> TextContent:
    reading = working_memory.get_stuff_as_str(name="reading")
    if _IS_LOST_ATTEMPT.get():
        msg = f"The worker condensing '{reading}' was lost"
        raise RuntimeError(msg)
    return TextContent(text=f"Condensed: {reading}")


class ItemExecutionRouter(PipeRouter):
    """Runs each batch item as an execution of its own, which a distributed engine may run again.

    The item's job crosses a serialization boundary first, as a child workflow's input does, and the item's execution
    opens its own tracer on the context it received, as the hosted run workflow does. The item named by
    `retried_item_segment` runs twice: its first attempt fails, and the engine runs a second, whose output the batch
    receives.

    Attributes:
        retried_item_segment: The segment of the item whose execution runs a second attempt.
        received_contexts: By item segment, the trace context each item's execution received.
    """

    def __init__(self, *, retried_item_segment: str) -> None:
        super().__init__()
        self.retried_item_segment = retried_item_segment
        self.received_contexts: dict[str, TraceContext] = {}

    @override
    async def run_batch_branch(self, pipe_job: PipeJob) -> PipeOutput:
        received_metadata = kajson.loads(kajson.dumps(pipe_job.job_metadata))
        assert isinstance(received_metadata, JobMetadata)
        received_context = received_metadata.trace_context
        assert received_context is not None
        assert received_context.child_segment is not None
        item_segment = received_context.child_segment
        self.received_contexts[item_segment] = received_context
        execution = f"exec-{item_segment}"
        if item_segment != self.retried_item_segment:
            return await self._run_attempt(pipe_job=pipe_job, received_metadata=received_metadata, execution=execution, attempt=1)

        lost_attempt_token = _IS_LOST_ATTEMPT.set(True)
        try:
            await self._run_attempt(pipe_job=pipe_job, received_metadata=received_metadata, execution=execution, attempt=1)
        except PipelexError:
            pass
        else:
            msg = f"The first attempt of {execution} was meant to fail"
            raise AssertionError(msg)
        finally:
            _IS_LOST_ATTEMPT.reset(lost_attempt_token)
        return await self._run_attempt(pipe_job=pipe_job, received_metadata=received_metadata, execution=execution, attempt=2)

    async def _run_attempt(self, *, pipe_job: PipeJob, received_metadata: JobMetadata, execution: str, attempt: int) -> PipeOutput:
        received_context = received_metadata.trace_context
        assert received_context is not None
        tracer_manager = GraphTracerManager.get_or_create_instance()
        tracer_key = f"{execution}@{attempt}"
        attempt_context = tracer_manager.open_tracer(
            graph_id=received_context.graph_id,
            data_inclusion=received_context.data_inclusion,
            event_log=get_event_log_override(),
            workflow_id=execution,
            attempt=attempt,
            received_context=received_context,
            pipeline_run_id=received_metadata.run_metadata.pipeline_run_id,
            tracer_key=tracer_key,
            run_mode=received_context.run_mode,
        )
        # Each attempt starts from the input the engine delivered, never from what an earlier attempt left behind.
        attempt_job = pipe_job.model_copy(
            update={
                "job_metadata": received_metadata.model_copy(update={"trace_context": attempt_context}),
                "working_memory": pipe_job.get_working_memory().make_deep_copy(),
            }
        )
        try:
            return await super().run_batch_branch(attempt_job)
        finally:
            tracer_manager.close_tracer(tracer_key)
