"""A lift-skip chain inside a PipeSequence: SubPipe's miss-gate tolerates recorded absences so
each step's own gate decides (skip / run / force). The absorbing `?` step sinks the taint before
the method boundary, so the sequence delivers a real main stuff (Step B scope).
"""

from typing import Callable, cast

import pytest
from mthds.protocol.pipeline_inputs import PipelineInputs

from pipelex.config import get_config
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.execution_seams import prepare_pipe_job
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry

_DOMAIN_CODE = "test_optionals_seq"


def optionals_seq_echo_source(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"a:{working_memory.get_stuff_as_str(name='source')}")


def optionals_seq_echo_a_out(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"b:{working_memory.get_stuff_as_str(name='a_out')}")


def optionals_seq_sink(working_memory: WorkingMemory) -> TextContent:
    topic = working_memory.get_stuff_as_str(name="topic")
    b_out_stuff = working_memory.get_optional_stuff(name="b_out")
    if b_out_stuff is None:
        return TextContent(text=f"report about {topic} (no analysis available)")
    return TextContent(text=f"report about {topic}: {b_out_stuff.as_text.text}")


_TEST_FUNCS = [optionals_seq_echo_source, optionals_seq_echo_a_out, optionals_seq_sink]


def _make_live_run_params() -> PipeRunParams:
    return PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=get_config().pipelex.pipe_run_config.pipe_stack_limit)


def _build_lift_sequence() -> PipeSequence:
    """Register the A -> B -> C(sink) step pipes in the library and build the sequence over them.

    The sequence declares `source = "Text?"` at its boundary while step A needs it plain — the
    declared-vs-needed comparison must not treat the presence marker as a spec mismatch.
    """
    step_a = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_seq_step_a",
        blueprint=PipeFuncBlueprint(
            description="Consumes the maybe-absent source (plain input): lifted when source is absent",
            inputs={"source": "Text"},
            output="Text",
            function_name="optionals_seq_echo_source",
        ),
    )
    step_b = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_seq_step_b",
        blueprint=PipeFuncBlueprint(
            description="Consumes step A's output (plain input): lifted in chain",
            inputs={"a_out": "Text"},
            output="Text",
            function_name="optionals_seq_echo_a_out",
        ),
    )
    sink_c = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_seq_sink_c",
        blueprint=PipeFuncBlueprint(
            description="Absorbing sink: declares b_out optional and handles both arms",
            inputs={"topic": "Text", "b_out": "Text?"},
            output="Text",
            function_name="optionals_seq_sink",
        ),
    )
    pipe_library = get_pipe_library()
    for pipe in [step_a, step_b, sink_c]:
        pipe_library.add_new_pipe(pipe=pipe)

    sequence = PipeFactory[PipeSequence].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="opt_lift_sequence",
        blueprint=PipeSequenceBlueprint(
            description="Lift chain: A and B skip when source is absent; C absorbs",
            inputs={"source": "Text?", "topic": "Text"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="opt_seq_step_a", result="a_out"),
                SubPipeBlueprint(pipe="opt_seq_step_b", result="b_out"),
                SubPipeBlueprint(pipe="opt_seq_sink_c", result="final_report"),
            ],
        ),
    )
    pipe_library.add_new_pipe(pipe=sequence)
    # The declared-vs-needed input check must accept the `?` boundary over a plain child need.
    sequence.validate_with_libraries()
    return sequence


@pytest.mark.asyncio(loop_scope="class")
class TestLiftSequence:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    async def test_sequence_lifts_steps_and_sinks_absence(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """With source absent (recorded), steps A and B skip with chained provenance and the
        absorbing sink C still delivers the sequence's main output.
        """
        load_empty_library()
        sequence = _build_lift_sequence()

        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            StuffFactory.make_from_str("penalties", name="topic"),
        )
        source_record = AbsenceRecord(
            variable_name="source",
            kind=AbsenceKind.NOT_PROVIDED,
            reason="optional input 'source' was not provided by the caller",
        )
        working_memory.record_absence(source_record)

        pipe_output = await sequence.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )

        # The sink ran on the absent arm and delivered the sequence's output.
        assert pipe_output.main_stuff.as_text.text == "report about penalties (no analysis available)"

        result_memory = pipe_output.working_memory
        a_record = result_memory.get_optional_absence("a_out")
        assert a_record is not None
        assert a_record.kind == AbsenceKind.SKIPPED
        assert a_record.producing_pipe == "opt_seq_step_a"
        assert a_record.upstream == source_record

        b_record = result_memory.get_optional_absence("b_out")
        assert b_record is not None
        assert b_record.kind == AbsenceKind.SKIPPED
        assert b_record.producing_pipe == "opt_seq_step_b"
        assert b_record.upstream == a_record

        # Run-report enumeration: the ledger lists exactly the genuinely absent slots — the
        # positional main-stuff record was superseded when the sink delivered a real output.
        assert set(result_memory.absences.keys()) == {"source", "a_out", "b_out"}

    async def test_lifted_step_honors_invocation_multiplicity_override(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """A singular-output pipe invoked with a plural override (`multiple_output = true` on the
        sub-pipe) normalizes its lifted output to the empty list — matching what the static taint
        pass promised downstream list consumers — instead of recording a singular absence.
        """
        load_empty_library()
        step_a = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="opt_seq_step_a",
            blueprint=PipeFuncBlueprint(
                description="Consumes the maybe-absent source (plain input): lifted when source is absent",
                inputs={"source": "Text"},
                output="Text",
                function_name="optionals_seq_echo_source",
            ),
        )
        working_memory = WorkingMemoryFactory.make_from_single_stuff(
            StuffFactory.make_from_str("penalties", name="topic"),
        )
        working_memory.record_absence(
            AbsenceRecord(
                variable_name="source",
                kind=AbsenceKind.NOT_PROVIDED,
                reason="optional input 'source' was not provided by the caller",
            ),
        )
        run_params = _make_live_run_params()
        # The invocation-level override a SubPipe applies (`multiple_output = true`).
        run_params.output_multiplicity = True

        pipe_output = await step_a.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=run_params,
            output_name="a_out",
        )

        result_memory = pipe_output.working_memory
        lifted_stuff = result_memory.get_optional_stuff("a_out")
        assert lifted_stuff is not None
        lifted_content = lifted_stuff.content
        assert isinstance(lifted_content, ListContent)
        assert cast("ListContent[TextContent]", lifted_content).items == []
        # The ledger keeps the observability note beside the empty-list value.
        note = result_memory.get_optional_absence("a_out")
        assert note is not None
        assert note.kind == AbsenceKind.SKIPPED

    async def test_sequence_runs_fully_when_source_provided(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """With source present, nothing is lifted and the sink gets the analysis arm."""
        load_empty_library()
        sequence = _build_lift_sequence()

        working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(
            [
                StuffFactory.make_from_str("clause 12", name="source"),
                StuffFactory.make_from_str("penalties", name="topic"),
            ],
        )

        pipe_output = await sequence.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )

        assert pipe_output.main_stuff.as_text.text == "report about penalties: b:a:clause 12"
        assert pipe_output.working_memory.absences == {}

    async def test_prepare_pipe_job_seeds_boundary_optional_from_declared_marker(self, load_empty_library: Callable[[], str]):
        """The not-provided record is seeded from the sequence's DECLARED `source = "Text?"`
        boundary, even though the aggregated needed-inputs carry step A's plain marker —
        and the whole method then runs end-to-end on the absent arm.
        """
        library_id = load_empty_library()
        sequence = _build_lift_sequence()

        pipe_job = await prepare_pipe_job(
            pipe=sequence,
            library_id=library_id,
            execution_config=get_config().pipelex.pipeline_execution_config,
            pipe_run_mode=PipeRunMode.LIVE,
            pipeline_run_id="test-optional-boundary-seeding",
            user_id="pytest",
            inputs=PipelineInputs({"topic": "penalties"}),
        )

        job_memory = pipe_job.working_memory
        assert job_memory is not None
        source_record = job_memory.get_optional_absence("source")
        assert source_record is not None
        assert source_record.kind == AbsenceKind.NOT_PROVIDED

        pipe_output = await sequence.run_pipe(
            job_metadata=pipe_job.job_metadata,
            working_memory=job_memory,
            pipe_run_params=pipe_job.pipe_run_params,
        )
        assert pipe_output.main_stuff.as_text.text == "report about penalties (no analysis available)"
