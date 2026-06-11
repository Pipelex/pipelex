"""Mode-1 Temporal guard: the in-process graph dry-run must stay in-process under a Temporal hub.

Phase-2 companion to ``test_validate_sweep_stays_in_process``: where that test proves the
*validation sweep* never dispatches to Temporal, this one proves the *graph-producing dry-run*
(``dry_run_pipe_in_process``) runs fully in-process and traces into an in-memory event log even
when the hub default router is the real ``TemporalPipeRouter`` and the hub default content
generator is ``ContentGeneratorInWorkflow`` (wired by this suite's ``boot_temporal`` fixture,
exactly as a Temporal-enabled worker/API process is wired).

Contract asserted (TODOS.md Phase 2):

- (a) a correct, non-empty ``GraphSpec`` comes back, covering the whole controller topology;
- (b) ZERO workflows/activities are dispatched (spy on ``WorkflowExecutor.execute_workflow``);
- (c) no file/DDB transport is touched (``make_event_log`` is forbidden — the scoped in-memory
  instance is the single transport);
- the zero-dispatch guarantee holds with the DRY mock at the LEAF (Part B): DRY routes through
  the hub-resolved content generator, so the scoped inline generator is what keeps the run
  in-process — this is what ``scoped_content_generator`` exists for;
- tracer-key alignment: emit and assemble share the ``pipeline_run_id`` partition by
  construction (a divergent key would yield an empty graph, so the non-empty assertion pins it).
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import clear_current_library, get_library_manager, get_pipelex_hub, get_required_pipe
from pipelex.pipe_run.dry_run_pipeline import dry_run_pipe_in_process
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor
from pipelex.temporal.tprl_content_generation.content_generator_in_workflow import ContentGeneratorInWorkflow
from pipelex.temporal.tprl_pipe.temporal_pipe_router import TemporalPipeRouter
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.tracing.trace_events import UsageReportEvent
from tests.integration.pipelex.temporal.test_data import PipeParallelTemporalTestData

_PARALLEL_MAIN_PIPE_REF = f"{PipeParallelTemporalTestData.DOMAIN}.{PipeParallelTemporalTestData.PIPE_CODE}"


@pytest.mark.temporal
@pytest.mark.asyncio(loop_scope="class")
class TestDryRunGraphInProcess:
    def _assert_temporal_hub_preconditions(self) -> None:
        """The hub defaults must be the REAL Temporal ones — that's the environment being guarded against."""
        hub = get_pipelex_hub()
        assert isinstance(hub.get_required_pipe_router(), TemporalPipeRouter), (
            "Temporal suite precondition: the hub default router must be the real TemporalPipeRouter"
        )
        assert isinstance(hub.get_required_content_generator(), ContentGeneratorInWorkflow), (
            "Temporal suite precondition: the hub default content generator must be ContentGeneratorInWorkflow"
        )

    def _forbid_event_log_factory(self, mocker: MockerFixture) -> None:
        factory_error = AssertionError("make_event_log must not be called: the in-process graph dry-run traces in memory only")
        mocker.patch("pipelex.pipeline.pipeline_run_setup.make_event_log", side_effect=factory_error)
        mocker.patch("pipelex.pipe_run.tracing_assembly.make_event_log", side_effect=factory_error)

    async def _run_in_process_graph_dry_run(self, library_id: str) -> GraphSpec:
        mthds_content = Path(PipeParallelTemporalTestData.BUNDLE_FILE).read_text(encoding="utf-8")
        acquire_library(library_id=library_id, mthds_contents=[mthds_content])
        try:
            main_pipe = get_required_pipe(pipe_code=_PARALLEL_MAIN_PIPE_REF)
            return await dry_run_pipe_in_process(pipe=main_pipe, library_id=library_id)
        finally:
            get_library_manager().teardown(library_id=library_id)
            clear_current_library()

    async def test_graph_dry_run_zero_dispatch_in_memory(self, mocker: MockerFixture) -> None:
        self._assert_temporal_hub_preconditions()
        execute_workflow_spy = mocker.spy(WorkflowExecutor, "execute_workflow")
        self._forbid_event_log_factory(mocker)
        emit_spy = mocker.spy(InMemoryEventLog, "emit")

        graph_spec = await self._run_in_process_graph_dry_run(library_id="dry_run_graph_in_process_lib")

        # (a) correct, non-empty GraphSpec covering the whole controller topology (sequence,
        # parallel fan-out, both branches, summary). Tracer-key alignment is pinned by the same
        # assertion: a divergent emit/assemble key would have produced an empty graph.
        traced_pipe_codes = {node.pipe_code for node in graph_spec.nodes if node.pipe_code}
        expected_pipe_codes = {pipe_ref.split(".")[-1] for pipe_ref in PipeParallelTemporalTestData.EXPECTED_PIPE_REFS}
        assert expected_pipe_codes <= traced_pipe_codes
        assert graph_spec.edges

        # (b) zero Temporal dispatch during the whole dry-run.
        execute_workflow_spy.assert_not_called()

        # (d) usage-event isolation (pre-flight decision 3): the dry leaves report synthetic
        # zero-token jobs, but the run's trace context has emit_usage_events=False, so no
        # UsageReportEvent ever reaches the (scoped, in-memory) transport — nothing leaks to any
        # ambient registry, and the events die with the run.
        emitted_events = [call.args[1] for call in emit_spy.call_args_list]
        assert emitted_events, "the dry-run must emit graph events through the scoped log"
        assert not [event for event in emitted_events if isinstance(event, UsageReportEvent)]

    async def test_leaf_level_mock_stays_in_process(self, mocker: MockerFixture) -> None:
        """Leaf-level DRY (Part B, now the real path): DRY routes through the hub-resolved
        generator and the cogt leaf mocks, so the scoped inline generator must keep the run
        in-process — without ``scoped_content_generator`` the leaf would reach the hub's
        ``ContentGeneratorInWorkflow`` and try to dispatch activities.
        """
        self._assert_temporal_hub_preconditions()
        execute_workflow_spy = mocker.spy(WorkflowExecutor, "execute_workflow")
        self._forbid_event_log_factory(mocker)
        # Prove the run actually used the scoped inline generator (not the hub default).
        inline_text_spy = mocker.spy(ContentGenerator, "make_llm_text")

        graph_spec = await self._run_in_process_graph_dry_run(library_id="dry_run_graph_leaf_mock_lib")

        assert graph_spec.nodes
        assert inline_text_spy.call_count >= 1
        execute_workflow_spy.assert_not_called()
