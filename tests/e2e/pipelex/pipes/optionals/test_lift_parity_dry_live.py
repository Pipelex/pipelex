"""Dry/live parity for a lifted chain loaded from a `.mthds` file: the lift gate is run-mode
independent, so a dry run (without mock inputs) must produce the same absence ledger and the same
skipped graph nodes as the live run.
"""

from pathlib import Path

import pytest

from pipelex.config import get_config
from pipelex.core.memory.absence import AbsenceRecord
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME
from pipelex.graph.graphspec import GraphSpec, GraphSpecMode, NodeStatus
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipeline.pipeline_response import RunState
from pipelex.pipeline.runner import PipelexMTHDSProtocol

_FIXTURE_DIR = Path(__file__).parent / "lift_parity"


def _skipped_nodes(graph_spec: GraphSpec) -> dict[str | None, str | None]:
    return {node.pipe_code: node.skip_reason for node in graph_spec.nodes if node.status == NodeStatus.SKIPPED}


@pytest.mark.asyncio(loop_scope="class")
class TestLiftedChainDryLiveParity:
    async def test_dry_and_live_absence_ledgers_and_skips_match(self):
        """Running the lift chain with the optional source omitted, live and dry (no mock
        seeding), yields identical ledgers (keys, kinds, producing pipes) and identical skipped
        graph nodes with the same skip reasons.
        """
        execution_config = get_config().pipelex.pipeline_execution_config.with_execution_overrides(generate_graph=True)

        live_runner = PipelexMTHDSProtocol(library_dirs=[str(_FIXTURE_DIR)], execution_config=execution_config)
        live_response = await live_runner.execute(pipe_code="opar_flow", inputs={})

        dry_runner = PipelexMTHDSProtocol(
            library_dirs=[str(_FIXTURE_DIR)],
            execution_config=execution_config,
            pipe_run_mode=PipeRunMode.DRY,
        )
        dry_response = await dry_runner.execute(pipe_code="opar_flow", inputs={})

        for response in [live_response, dry_response]:
            assert response.state == RunState.COMPLETED
            assert response.main_stuff_name == "summary"
            assert isinstance(response.pipe_output.working_memory.resolve_main_stuff(), AbsenceRecord)

        live_memory = live_response.pipe_output.working_memory
        dry_memory = dry_response.pipe_output.working_memory
        # The absent main output records under its slot name AND the positional main-stuff key.
        assert set(live_memory.absences.keys()) == set(dry_memory.absences.keys()) == {"source", "analysis", "summary", MAIN_STUFF_NAME}
        for name in live_memory.absences:
            live_record = live_memory.absences[name]
            dry_record = dry_memory.absences[name]
            assert live_record.kind == dry_record.kind
            assert live_record.producing_pipe == dry_record.producing_pipe

        live_graph = live_response.pipe_output.graph_spec
        dry_graph = dry_response.pipe_output.graph_spec
        assert live_graph is not None
        assert dry_graph is not None
        assert live_graph.meta["mode"] == GraphSpecMode.LIVE
        assert dry_graph.meta["mode"] == GraphSpecMode.DRY
        live_skips = _skipped_nodes(live_graph)
        dry_skips = _skipped_nodes(dry_graph)
        assert set(live_skips.keys()) == set(dry_skips.keys()) == {"opar_make_analysis", "opar_summarize"}
        for pipe_code, live_skip_reason in live_skips.items():
            assert live_skip_reason is not None
            assert live_skip_reason == dry_skips[pipe_code]

        live_controller_statuses = {node.pipe_code: node.status for node in live_graph.nodes}
        dry_controller_statuses = {node.pipe_code: node.status for node in dry_graph.nodes}
        assert live_controller_statuses["opar_flow"] == NodeStatus.SUCCEEDED
        assert dry_controller_statuses["opar_flow"] == NodeStatus.SUCCEEDED
