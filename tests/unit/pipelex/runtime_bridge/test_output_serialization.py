from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.runtime_bridge.bridge import (
    _serialize_completed_output,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
)


class TestSerializeCompletedOutput:
    def test_assembly_results_and_errors_cross_the_bridge_boundary(self) -> None:
        """tokens_usages + both assembly-error strings are propagated onto the boundary DTO.

        Mirrors graph_spec: a run can aggregate usage / fail assembly and must not drop
        that at the JSON boundary, or host runtimes can't render the end-of-run cost
        report or tell an assembly failure apart from assembly being off.
        """
        pipe_output = PipeOutput(
            working_memory=WorkingMemory(),
            pipeline_run_id="run-with-usage",
            tokens_usages=[],
            usage_assembly_error="usage boom",
            graph_assembly_error="graph boom",
        )

        dto = _serialize_completed_output(
            pipe_output=pipe_output,
            workflow_id=None,
        )

        assert dto.tokens_usages_dump == []
        assert dto.usage_assembly_error == "usage boom"
        assert dto.graph_assembly_error == "graph boom"
        assert dto.pipeline_run_id == "run-with-usage"
        assert dto.is_completed is True

    def test_absent_assembly_serializes_to_none(self) -> None:
        """When the run produced no usage/graph, the boundary fields stay None (not [])."""
        pipe_output = PipeOutput(
            working_memory=WorkingMemory(),
            pipeline_run_id="run-without-usage",
        )

        dto = _serialize_completed_output(
            pipe_output=pipe_output,
            workflow_id=None,
        )

        assert dto.tokens_usages_dump is None
        assert dto.usage_assembly_error is None
        assert dto.graph_assembly_error is None
