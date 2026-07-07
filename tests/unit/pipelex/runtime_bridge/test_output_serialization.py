import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.runtime_bridge.serialization import resolve_main_stuff_root_key, serialize_completed_output


def _make_stuff(name: str) -> Stuff:
    return Stuff(
        stuff_code=f"code-{name}",
        stuff_name=name,
        concept=Concept(
            code="Text",
            domain_code="native",
            description="Plain text",
            structure_class_name="TextContent",
        ),
        content=TextContent(text="hello"),
    )


def _memory_with_aliased_main(name: str) -> WorkingMemory:
    return WorkingMemory(root={name: _make_stuff(name)}, aliases={MAIN_STUFF_NAME: name})


class TestSerializeCompletedOutput:
    def test_assembly_results_and_errors_cross_the_bridge_boundary(self) -> None:
        """tokens_usages + both assembly-error strings are propagated onto the boundary DTO.

        Mirrors graph_spec: a run can aggregate usage / fail assembly and must not drop
        that at the JSON boundary, or host runtimes can't render the end-of-run cost
        report or tell an assembly failure apart from assembly being off.
        """
        pipe_output = PipeOutput(
            working_memory=_memory_with_aliased_main("result"),
            pipeline_run_id="run-with-usage",
            tokens_usages=[],
            usage_assembly_error="usage boom",
            graph_assembly_error="graph boom",
        )

        dto = serialize_completed_output(
            pipe_output=pipe_output,
            workflow_id=None,
        )

        assert dto.tokens_usages_dump == []
        assert dto.usage_assembly_error == "usage boom"
        assert dto.graph_assembly_error == "graph boom"
        assert dto.pipeline_run_id == "run-with-usage"

    def test_absent_assembly_serializes_to_none(self) -> None:
        """When the run produced no usage/graph, the boundary fields stay None (not [])."""
        pipe_output = PipeOutput(
            working_memory=_memory_with_aliased_main("result"),
            pipeline_run_id="run-without-usage",
        )

        dto = serialize_completed_output(
            pipe_output=pipe_output,
            workflow_id=None,
        )

        assert dto.tokens_usages_dump is None
        assert dto.usage_assembly_error is None
        assert dto.graph_assembly_error is None

    def test_main_stuff_name_resolves_aliased_root_key(self) -> None:
        """The DTO's main_stuff_name is the actual root key the alias points at."""
        pipe_output = PipeOutput(
            working_memory=_memory_with_aliased_main("final_result"),
            pipeline_run_id="run-aliased",
        )

        dto = serialize_completed_output(pipe_output=pipe_output, workflow_id=None)

        assert dto.main_stuff_name == "final_result"

    def test_main_stuff_name_resolves_direct_root_key(self) -> None:
        """When the main stuff sits directly at root[MAIN_STUFF_NAME], that key is returned."""
        memory = WorkingMemory(root={MAIN_STUFF_NAME: _make_stuff(MAIN_STUFF_NAME)})
        pipe_output = PipeOutput(working_memory=memory, pipeline_run_id="run-direct")

        assert resolve_main_stuff_root_key(pipe_output=pipe_output) == MAIN_STUFF_NAME

    def test_missing_main_stuff_raises(self) -> None:
        """A completed run always resolves its declared output — a working memory with neither a
        value nor a recorded absence at this boundary is a contract violation.
        """
        pipe_output = PipeOutput(
            working_memory=WorkingMemory(),
            pipeline_run_id="run-broken",
        )

        with pytest.raises(PipeJobError):
            serialize_completed_output(pipe_output=pipe_output, workflow_id=None)

    def test_absent_main_output_resolves_declared_slot_name(self) -> None:
        """A run whose main output resolved absent is a success: main_stuff_name names the
        declared output slot and the serialized output_dict carries the absence records —
        consumers branch on the record, never on transport.
        """
        memory = WorkingMemory()
        record = AbsenceRecord(
            variable_name="summary",
            kind=AbsenceKind.SKIPPED,
            reason="skipped because input 'analysis' is absent",
            producing_pipe="summarize",
        )
        memory.record_new_main_absence(record)
        pipe_output = PipeOutput(working_memory=memory, pipeline_run_id="run-absent")

        assert resolve_main_stuff_root_key(pipe_output=pipe_output) == "summary"

        dto = serialize_completed_output(pipe_output=pipe_output, workflow_id=None)
        assert dto.main_stuff_name == "summary"
        serialized_record = dto.output_dict["absences"]["summary"]
        assert serialized_record["kind"] == "skipped"
        assert serialized_record["producing_pipe"] == "summarize"
        # The positional main-stuff key marks the absence as the run's resolved main result.
        assert dto.output_dict["absences"][MAIN_STUFF_NAME]["variable_name"] == "summary"
