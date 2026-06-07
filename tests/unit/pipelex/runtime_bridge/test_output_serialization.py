from typing import TYPE_CHECKING, cast

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.runtime_bridge.bridge import (
    _serialize_completed_output,  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from pipelex.pipe_run.pipe_job import PipeJob


class TestSerializeCompletedOutput:
    def test_usage_fields_cross_the_bridge_boundary(self) -> None:
        """tokens_usages / usage_assembly_error are propagated onto the boundary DTO.

        Mirrors graph_spec: a run can aggregate usage and must not drop it at the
        JSON boundary, or host runtimes can't render the end-of-run cost report.
        """
        pipe_output = PipeOutput(
            working_memory=WorkingMemory(),
            pipeline_run_id="run-with-usage",
            tokens_usages=[],
            usage_assembly_error="assembly boom",
        )

        dto = _serialize_completed_output(
            pipe_output=pipe_output,
            pipe_job=cast("PipeJob", None),
            workflow_id=None,
        )

        assert dto.tokens_usages_dump == []
        assert dto.usage_assembly_error == "assembly boom"
        assert dto.pipeline_run_id == "run-with-usage"
        assert dto.is_completed is True

    def test_absent_usage_serializes_to_none(self) -> None:
        """When the run produced no usage, the boundary fields stay None (not [])."""
        pipe_output = PipeOutput(
            working_memory=WorkingMemory(),
            pipeline_run_id="run-without-usage",
        )

        dto = _serialize_completed_output(
            pipe_output=pipe_output,
            pipe_job=cast("PipeJob", None),
            workflow_id=None,
        )

        assert dto.tokens_usages_dump is None
        assert dto.usage_assembly_error is None
