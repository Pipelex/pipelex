"""Runtime trichotomy on absent inputs (D3): a plain input fed a recorded absence lifts (skips)
the pipe with provenance; a `?` input runs; a `!` input raises a typed error carrying the chain.
A missing input with no absence record stays a hard PipeRunInputsError — that is the bug case.

All tests run PipeFunc pipes live (no inference) and sink absence before any method boundary.
"""

from typing import Callable, cast

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.exceptions import OptionalValueAbsentError, PipeRunInputsError
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry
from tests.unit.pipelex.graph.conftest import make_trace_context


def optionals_echo_source(working_memory: WorkingMemory) -> TextContent:
    source_text = working_memory.get_stuff_as_str(name="source")
    return TextContent(text=f"echo:{source_text}")


def optionals_absorbing_sink(working_memory: WorkingMemory) -> TextContent:
    source_stuff = working_memory.get_optional_stuff(name="source")
    if source_stuff is None:
        return TextContent(text="report:source-absent")
    return TextContent(text=f"report:{source_stuff.as_text.text}")


def optionals_list_from_source(working_memory: WorkingMemory) -> ListContent[TextContent]:
    source_text = working_memory.get_stuff_as_str(name="source")
    return ListContent[TextContent](items=[TextContent(text=source_text)])


_TEST_FUNCS = [optionals_echo_source, optionals_absorbing_sink, optionals_list_from_source]


def _make_pipe_func(pipe_code: str, *, source_ref: str, function_name: str = "optionals_echo_source", output: str = "Text") -> PipeFunc:
    blueprint = PipeFuncBlueprint(
        description=f"Optionals trichotomy test pipe {pipe_code}",
        inputs={"source": source_ref},
        output=output,
        function_name=function_name,
    )
    return PipeFactory[PipeFunc].make_from_blueprint(
        domain_code="test_optionals",
        pipe_code=pipe_code,
        blueprint=blueprint,
    )


def _make_source_stuff(text: str = "hello") -> Stuff:
    return StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
        content=TextContent(text=text),
        name="source",
    )


def _make_seeded_absence() -> AbsenceRecord:
    return AbsenceRecord(
        variable_name="source",
        kind=AbsenceKind.DECLARED_ABSENT,
        reason="no penalty clause found in this contract",
        producing_pipe="extract_penalty_clause",
    )


def _make_live_run_params() -> PipeRunParams:
    # Constructed directly (not via the factory) so a keyless boot's forced-DRY coercion cannot
    # silently swap which code path (live vs dry) the test exercises.
    return PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=get_config().pipelex.pipe_run_config.pipe_stack_limit)


@pytest.mark.asyncio(loop_scope="class")
class TestLiftSkipTrichotomy:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    async def test_plain_input_absent_with_record_lifts_pipe(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """A plain input fed a recorded absence skips the pipe and records a chained skipped-absence."""
        load_empty_library()
        pipe = _make_pipe_func("opt_plain_consumer", source_ref="Text")
        seeded = _make_seeded_absence()
        working_memory = WorkingMemoryFactory.make_empty()
        working_memory.record_absence(seeded)

        pipe_output = await pipe.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
            output_name="echoed",
        )

        result_memory = pipe_output.working_memory
        assert result_memory.get_optional_stuff("echoed") is None
        skipped_record = result_memory.get_optional_absence("echoed")
        assert skipped_record is not None
        assert skipped_record.kind == AbsenceKind.SKIPPED
        assert skipped_record.producing_pipe == "opt_plain_consumer"
        assert "source" in skipped_record.reason
        assert skipped_record.upstream == seeded
        # The skipped pipe's output is the resolved-as-absent main result.
        resolved_main = result_memory.resolve_main_stuff()
        assert isinstance(resolved_main, AbsenceRecord)
        assert result_memory.get_optional_main_stuff() is None
        # Run identity is stamped like on every other path.
        assert pipe_output.pipeline_run_id == job_metadata.pipeline_run_id

    async def test_lift_chain_provenance(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """Two lifted pipes in a row chain their skipped-absence records back to the origin."""
        load_empty_library()
        pipe_first = _make_pipe_func("opt_chain_first", source_ref="Text")
        blueprint_second = PipeFuncBlueprint(
            description="Second chained consumer",
            inputs={"echoed": "Text"},
            output="Text",
            function_name="optionals_absorbing_sink",
        )
        pipe_second = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code="test_optionals",
            pipe_code="opt_chain_second",
            blueprint=blueprint_second,
        )
        seeded = _make_seeded_absence()
        working_memory = WorkingMemoryFactory.make_empty()
        working_memory.record_absence(seeded)

        first_output = await pipe_first.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
            output_name="echoed",
        )
        second_output = await pipe_second.run_pipe(
            job_metadata=job_metadata,
            working_memory=first_output.working_memory,
            pipe_run_params=_make_live_run_params(),
            output_name="final",
        )

        final_record = second_output.working_memory.get_optional_absence("final")
        assert final_record is not None
        assert final_record.kind == AbsenceKind.SKIPPED
        chain = final_record.provenance_chain()
        assert [record.variable_name for record in chain] == ["final", "echoed", "source"]
        assert final_record.origin() == seeded

    async def test_optional_input_absent_runs_pipe(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """A `?` input absorbs absence: the pipe runs and the taint terminates."""
        load_empty_library()
        pipe = _make_pipe_func("opt_absorber", source_ref="Text?", function_name="optionals_absorbing_sink")
        working_memory = WorkingMemoryFactory.make_empty()
        working_memory.record_absence(_make_seeded_absence())

        pipe_output = await pipe.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
            output_name="report",
        )

        assert pipe_output.main_stuff.as_text.text == "report:source-absent"
        assert pipe_output.working_memory.get_optional_absence("report") is None

    async def test_force_input_absent_raises_typed_error(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """A `!` input on a recorded absence raises OptionalValueAbsentError naming the variable,
        the consuming pipe, the producing pipe, and the original reason (D9 failure UX).
        """
        load_empty_library()
        pipe = _make_pipe_func("opt_forcer", source_ref="Text!")
        working_memory = WorkingMemoryFactory.make_empty()
        working_memory.record_absence(_make_seeded_absence())

        with pytest.raises(OptionalValueAbsentError) as exc_info:
            await pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=_make_live_run_params(),
            )

        error = exc_info.value
        message = str(error)
        assert "source" in message
        assert "opt_forcer" in message
        assert "extract_penalty_clause" in message
        assert "no penalty clause found in this contract" in message
        assert error.variable_name == "source"
        assert error.pipe_code == "opt_forcer"
        assert error.absence_record.origin().producing_pipe == "extract_penalty_clause"

    async def test_force_input_present_runs(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """`!` on a present value is a no-op assertion: the pipe runs normally."""
        load_empty_library()
        pipe = _make_pipe_func("opt_forcer_fed", source_ref="Text!")
        working_memory = WorkingMemoryFactory.make_from_single_stuff(_make_source_stuff("hello"))

        pipe_output = await pipe.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
        )
        assert pipe_output.main_stuff.as_text.text == "echo:hello"

    async def test_missing_without_record_still_raises_inputs_error(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """Absent with no record is a genuine miss: PipeRunInputsError, whose live-path message
        no longer claims to be a dry run (pre-existing message bug fixed in Step B).
        """
        load_empty_library()
        pipe = _make_pipe_func("opt_no_record", source_ref="Text")
        working_memory = WorkingMemoryFactory.make_empty()

        with pytest.raises(PipeRunInputsError) as exc_info:
            await pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=_make_live_run_params(),
            )
        message = str(exc_info.value)
        assert "source" in message
        assert "Dry run" not in message

    async def test_skipped_plural_output_normalizes_to_empty_list(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """A lifted pipe with plural output writes an empty ListContent (plus a ledger note),
        not an absent slot — taint stops there (D4).
        """
        load_empty_library()
        pipe = _make_pipe_func(
            "opt_plural_consumer",
            source_ref="Text",
            function_name="optionals_list_from_source",
            output="Text[]",
        )
        working_memory = WorkingMemoryFactory.make_empty()
        working_memory.record_absence(_make_seeded_absence())

        pipe_output = await pipe.run_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
            output_name="items",
        )

        result_memory = pipe_output.working_memory
        items_stuff = result_memory.get_optional_stuff("items")
        assert items_stuff is not None
        list_content = items_stuff.content
        assert isinstance(list_content, ListContent)
        assert cast("ListContent[TextContent]", list_content).items == []
        # The value wins for consumers; the ledger note stays for observability.
        assert isinstance(result_memory.resolve_stuff("items"), Stuff)
        note = result_memory.get_optional_absence("items")
        assert note is not None
        assert note.kind == AbsenceKind.SKIPPED
        # The empty list is a real output: it is the main stuff.
        assert pipe_output.main_stuff.stuff_name == "items"

    async def test_lifted_pipe_under_tracer_ends_node_skipped(
        self, job_metadata: JobMetadata, load_empty_library: Callable[[], str], mocker: MockerFixture
    ):
        """The graph-tracer epilogue fires on every pipe run: a lifted pipe ends its node in the
        distinct `skipped` state with the skip reason (Step E) — never a crash, never an error node.
        """
        load_empty_library()
        pipe = _make_pipe_func("opt_lift_traced", source_ref="Text")
        working_memory = WorkingMemoryFactory.make_empty()
        working_memory.record_absence(_make_seeded_absence())

        mock_manager = mocker.MagicMock()
        mock_manager.on_pipe_start = mocker.MagicMock(return_value=("node-1", None))
        mocker.patch(
            "pipelex.core.pipes.pipe_abstract.GraphTracerManager.get_instance",
            return_value=mock_manager,
        )
        traced_metadata = JobMetadata(
            user_id="pytest",
            pipeline_run_id=job_metadata.pipeline_run_id,
            trace_context=make_trace_context(graph_id=job_metadata.pipeline_run_id),
        )

        pipe_output = await pipe.run_pipe(
            job_metadata=traced_metadata,
            working_memory=working_memory,
            pipe_run_params=_make_live_run_params(),
            output_name="echoed",
        )

        assert isinstance(pipe_output.working_memory.resolve_main_stuff(), AbsenceRecord)
        mock_manager.on_pipe_end_skipped.assert_called_once()
        assert "source" in mock_manager.on_pipe_end_skipped.call_args.kwargs["skip_reason"]
        mock_manager.on_pipe_end_success.assert_not_called()
        mock_manager.on_pipe_end_error.assert_not_called()
