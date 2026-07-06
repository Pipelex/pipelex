"""When a whole `add_each_output` PipeParallel is lifted, every branch result slot it would
have written must be RESOLVED, not just the combined output: a recorded absence for singular
branch slots, an empty list for plural ones (D4). Otherwise a downstream consumer that the
static taint pass blessed meets a neither-value-nor-record hard miss at its gate.
"""

from typing import Callable, cast

import pytest

from pipelex.config import get_config
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_factory import PipeFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_pipe_library
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry

_DOMAIN_CODE = "test_optionals_companion"


def optionals_comp_find(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"found:{working_memory.get_stuff_as_str(name='source')}")


def optionals_comp_find_many(working_memory: WorkingMemory) -> ListContent[TextContent]:
    return ListContent[TextContent](items=[TextContent(text=f"item:{working_memory.get_stuff_as_str(name='source')}")])


def optionals_comp_sink(working_memory: WorkingMemory) -> TextContent:
    a_out_stuff = working_memory.get_optional_stuff(name="a_out")
    if a_out_stuff is None:
        return TextContent(text="no findings")
    return TextContent(text=f"findings: {a_out_stuff.as_text.text}")


_TEST_FUNCS = [optionals_comp_find, optionals_comp_find_many, optionals_comp_sink]


def _make_live_run_params() -> PipeRunParams:
    return PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=get_config().pipelex.pipe_run_config.pipe_stack_limit)


def _build_sequence_with_liftable_parallel() -> PipeSequence:
    """The parallel declares `source` PLAIN, so an absent `source` lifts it wholesale; its
    branch slots (`a_out` singular, `many_out` plural) land in the sequence flow via
    add_each_output; the sink absorbs `a_out` with a `?` input.
    """
    branch_single = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="comp_find",
        blueprint=PipeFuncBlueprint(
            description="Singular branch over source",
            inputs={"source": "Text"},
            output="Text",
            function_name="optionals_comp_find",
        ),
    )
    branch_plural = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="comp_find_many",
        blueprint=PipeFuncBlueprint(
            description="Plural branch over source",
            inputs={"source": "Text"},
            output="Text[]",
            function_name="optionals_comp_find_many",
        ),
    )
    sink = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="comp_sink",
        blueprint=PipeFuncBlueprint(
            description="Absorbs the singular branch slot",
            inputs={"a_out": "Text?"},
            output="Text",
            function_name="optionals_comp_sink",
        ),
    )
    parallel = PipeFactory[PipeParallel].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="comp_parallel",
        blueprint=PipeParallelBlueprint(
            description="Lifted wholesale when source is absent",
            inputs={"source": "Text"},
            output="Composite",
            branches=[
                SubPipeBlueprint(pipe="comp_find", result="a_out"),
                SubPipeBlueprint(pipe="comp_find_many", result="many_out"),
            ],
            add_each_output=True,
        ),
    )
    pipe_library = get_pipe_library()
    for pipe in [branch_single, branch_plural, sink, parallel]:
        pipe_library.add_new_pipe(pipe=pipe)
    sequence = PipeFactory[PipeSequence].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="comp_sequence",
        blueprint=PipeSequenceBlueprint(
            description="Lifted parallel then absorbing sink",
            inputs={"source": "Text?"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="comp_parallel", result="combined"),
                SubPipeBlueprint(pipe="comp_sink", result="final_report"),
            ],
        ),
    )
    pipe_library.add_new_pipe(pipe=sequence)
    return sequence


@pytest.mark.asyncio(loop_scope="class")
class TestLiftedParallelCompanionSlots:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    async def test_lifted_parallel_resolves_branch_slots(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """Static validation blesses the flow AND the runtime resolves every branch slot on lift:
        singular → SKIPPED record with provenance; plural → empty list. The absorbing sink runs.
        """
        load_empty_library()
        sequence = _build_sequence_with_liftable_parallel()
        # The static pass must accept exactly what the runtime produces.
        sequence.validate_with_libraries()

        working_memory = WorkingMemoryFactory.make_from_single_stuff(StuffFactory.make_from_str("penalties", name="topic"))
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

        assert pipe_output.main_stuff.as_text.text == "no findings"

        result_memory = pipe_output.working_memory
        # Singular branch slot: recorded absent with provenance chaining to the source record.
        a_out_record = result_memory.get_optional_absence("a_out")
        assert a_out_record is not None
        assert a_out_record.kind == AbsenceKind.SKIPPED
        assert a_out_record.producing_pipe == "comp_find"
        assert a_out_record.upstream == source_record
        assert result_memory.get_optional_stuff("a_out") is None
        # Plural branch slot: guaranteed empty list (D4), with an observability note.
        many_out_stuff = result_memory.get_optional_stuff("many_out")
        assert many_out_stuff is not None
        many_out_content = many_out_stuff.content
        assert isinstance(many_out_content, ListContent)
        assert cast("ListContent[TextContent]", many_out_content).items == []
