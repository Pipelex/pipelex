"""F1 invariant for the Temporal ``WfPipeRun`` assembly path (Step 2).

Mirrors the DIRECT-mode coverage in
``tests/integration/pipelex/pipeline/test_direct_tracing_assembly.py`` for the
TEMPORAL arm. A full ``WfPipeRun`` run wraps the real ``WfPipeRouter`` as a child
and then runs Step 2's ``act_assemble_tracing``; the assembled artifacts must ride
back on ``pipe_output`` per the run's emit flags:

- **costs-only (``emit_graph_events=False, emit_usage_events=True``):** usage rides
  back on ``tokens_usages`` but ``graph_spec`` stays None. This is the exact
  DIRECT/TEMPORAL symmetry F1 guards — both the ``WfPipeRun`` Step-2 dispatch
  (``assemble_graph=False`` → activity returns ``graph_spec=None``) and the
  ``WfPipeRouter`` finally assignment must avoid producing a GraphSpec under
  ``--no-graph``.
- **graph+costs:** both ``graph_spec`` and ``tokens_usages`` populated.
- **graph-only (``emit_usage_events=False``):** ``graph_spec`` populated,
  ``tokens_usages`` stays None.

Runs fully dry (``PipeRunMode.DRY``, the default for ``sequence_tracing_job``) so no
inference happens; the dry content generator reports token usage inline, which is
what populates the usage stream that ``act_assemble_tracing`` aggregates.
"""

import uuid

import pytest
from temporalio.client import Client as TemporalClient

from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.temporal.temporal_hub import get_task_manager
from pipelex.temporal.tprl_pipe.pipe_run_arg import PipeRunArg
from pipelex.temporal.tprl_pipe.wf_pipe_run import WfPipeRun
from tests.integration.pipelex.temporal.library_crate.helpers import rehydrate_pipe_output
from tests.integration.pipelex.temporal.tracing.helpers import inject_trace_context


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestWfPipeRunTracingAssembly:
    async def _run(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
        *,
        emit_graph_events: bool,
        emit_usage_events: bool,
    ) -> PipeOutput:
        """Run a full ``WfPipeRun`` (router child + Step-2 assembly) on a single worker."""
        execution_run_id = f"wfrun_assembly_{uuid.uuid4().hex[:12]}"
        execution_job = inject_trace_context(
            sequence_tracing_job,
            execution_run_id,
            emit_graph_events=emit_graph_events,
            emit_usage_events=emit_usage_events,
        )
        pipe_run_arg = PipeRunArg(pipe_job=execution_job).prepare_for_temporal()
        task_queue = str(uuid.uuid4())
        workflow_id = str(uuid.uuid4())

        async with get_task_manager().make_worker(
            temporal_client,
            task_queue=task_queue,
            is_not_sandboxed=True,
        ):
            pipe_output: PipeOutput = await temporal_client.execute_workflow(  # pyright: ignore[reportUnknownMemberType]
                workflow=WfPipeRun.run,
                arg=pipe_run_arg,
                id=workflow_id,
                task_queue=task_queue,
            )

        rehydrate_pipe_output(pipe_output, pipe_job=sequence_tracing_job)
        return pipe_output

    async def test_costs_only_leaves_graph_spec_none(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """F1 (TEMPORAL): a costs-only run rides usage back but must leave graph_spec None."""
        pipe_output = await self._run(
            sequence_tracing_job,
            temporal_client,
            emit_graph_events=False,
            emit_usage_events=True,
        )

        assert pipe_output.graph_spec is None, "costs-only WfPipeRun must not produce a GraphSpec under --no-graph"
        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1

    async def test_graph_and_costs_populate_both(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """Positive control: with both concerns on, both artifacts ride back (so the costs-only assertion is not vacuous)."""
        pipe_output = await self._run(
            sequence_tracing_job,
            temporal_client,
            emit_graph_events=True,
            emit_usage_events=True,
        )

        assert pipe_output.graph_spec is not None
        assert pipe_output.tokens_usages is not None
        assert len(pipe_output.tokens_usages) >= 1

    async def test_graph_only_leaves_tokens_usages_none(
        self,
        sequence_tracing_job: PipeJob,
        temporal_client: TemporalClient,
    ) -> None:
        """The mirror asymmetry: graph-only assembles a GraphSpec but never sets tokens_usages."""
        pipe_output = await self._run(
            sequence_tracing_job,
            temporal_client,
            emit_graph_events=True,
            emit_usage_events=False,
        )

        assert pipe_output.graph_spec is not None
        assert pipe_output.tokens_usages is None
