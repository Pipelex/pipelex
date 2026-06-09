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
- the zero-dispatch guarantee holds with the DRY mock at the LEAF (Part-B simulation: the leaf
  resolves its content generator through ``get_content_generator()`` instead of constructing
  ``ContentGeneratorDry`` inline) — this is what ``scoped_content_generator`` exists for;
- tracer-key alignment: emit and assemble share the ``pipeline_run_id`` partition by
  construction (a divergent key would yield an empty graph, so the non-empty assertion pins it).
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.content_generator_dry import ContentGeneratorDry
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import clear_current_library, get_library_manager, get_pipelex_hub, get_required_pipe
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM, PipeLLMOutput
from pipelex.pipe_run.dry_run_pipeline import dry_run_pipe_in_process
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.tprl.workflow_caller import WorkflowExecutor
from pipelex.temporal.tprl_content_generation.content_generator_in_workflow import ContentGeneratorInWorkflow
from pipelex.temporal.tprl_pipe.temporal_pipe_router import TemporalPipeRouter
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

    async def test_leaf_level_mock_stays_in_process(self, mocker: MockerFixture) -> None:
        """Part-B simulation: with the DRY mock relocated to the leaf (the leaf resolves
        ``get_content_generator()`` instead of constructing ``ContentGeneratorDry`` inline),
        the scoped inline generator must keep the run in-process — without
        ``scoped_content_generator`` the leaf would reach the hub's
        ``ContentGeneratorInWorkflow`` and try to dispatch activities.
        """
        self._assert_temporal_hub_preconditions()
        execute_workflow_spy = mocker.spy(WorkflowExecutor, "execute_workflow")
        self._forbid_event_log_factory(mocker)
        # Future-leaf shape: DRY delegates to the hub-resolved generator (content_generator=None
        # → get_content_generator()), exactly what Part B will do at the leaf.
        original_live_run = PipeLLM._live_run_operator_pipe  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

        async def dry_run_via_hub_generator(
            self: PipeLLM,
            job_metadata: JobMetadata,
            working_memory: WorkingMemory,
            pipe_run_params: PipeRunParams,
            output_name: str | None = None,
        ) -> PipeLLMOutput:
            return await original_live_run(
                self,
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=pipe_run_params,
                output_name=output_name,
                content_generator=None,
            )

        mocker.patch.object(PipeLLM, "_dry_run_operator_pipe", dry_run_via_hub_generator)
        # Prove the leaf actually used the scoped inline dry generator (not the hub default).
        dry_text_spy = mocker.spy(ContentGeneratorDry, "make_llm_text")

        graph_spec = await self._run_in_process_graph_dry_run(library_id="dry_run_graph_leaf_mock_lib")

        assert graph_spec.nodes
        assert dry_text_spy.call_count >= 1
        execute_workflow_spy.assert_not_called()
