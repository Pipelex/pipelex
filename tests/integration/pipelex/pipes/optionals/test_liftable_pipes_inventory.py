"""Liftable-pipe inventory (D3 phase-1 commitment): the valid report carries structured data
listing every pipe that may be skipped (lifted) when an optional slot is absent — the build-time
visibility that makes implicit lifting acceptable.
"""

from typing import Callable

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipeline.controller_taint import collect_controller_taint_analyses
from pipelex.pipeline.liftable_pipes import build_liftable_pipes
from pipelex.pipeline.validation_report import PipelexValidationReport
from pipelex.system.registries.func_registry import func_registry

_DOMAIN_CODE = "test_optionals_inventory"


def optionals_inv_echo_source(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"a:{working_memory.get_stuff_as_str(name='source')}")


def optionals_inv_echo_a_out(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"b:{working_memory.get_stuff_as_str(name='a_out')}")


def optionals_inv_sink(working_memory: WorkingMemory) -> TextContent:
    b_out_stuff = working_memory.get_optional_stuff(name="b_out")
    return TextContent(text="ok" if b_out_stuff is None else b_out_stuff.as_text.text)


def optionals_inv_echo_topic(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"base:{working_memory.get_stuff_as_str(name='topic')}")


_TEST_FUNCS = [optionals_inv_echo_source, optionals_inv_echo_a_out, optionals_inv_sink, optionals_inv_echo_topic]


def _build_lift_chain_pipes() -> list[str]:
    """Register the lift-chain sequence (A and B liftable, C absorbs) and return the pipe codes."""
    step_a = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="inv_step_a",
        blueprint=PipeFuncBlueprint(
            description="Liftable when source is absent",
            inputs={"source": "Text"},
            output="Text",
            function_name="optionals_inv_echo_source",
        ),
    )
    step_b = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="inv_step_b",
        blueprint=PipeFuncBlueprint(
            description="Liftable in chain",
            inputs={"a_out": "Text"},
            output="Text",
            function_name="optionals_inv_echo_a_out",
        ),
    )
    sink_c = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="inv_sink_c",
        blueprint=PipeFuncBlueprint(
            description="Absorbing sink",
            inputs={"b_out": "Text?"},
            output="Text",
            function_name="optionals_inv_sink",
        ),
    )
    pipe_library = get_pipe_library()
    for pipe in [step_a, step_b, sink_c]:
        pipe_library.add_new_pipe(pipe=pipe)
    sequence = PipeFactory[PipeSequence].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="inv_sequence",
        blueprint=PipeSequenceBlueprint(
            description="Lift chain",
            inputs={"source": "Text?"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="inv_step_a", result="a_out"),
                SubPipeBlueprint(pipe="inv_step_b", result="b_out"),
                SubPipeBlueprint(pipe="inv_sink_c", result="final_report"),
            ],
        ),
    )
    pipe_library.add_new_pipe(pipe=sequence)
    return ["inv_sequence", "inv_step_a", "inv_step_b", "inv_sink_c"]


class TestLiftablePipesInventory:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    def test_sequence_lift_chain_is_inventoried(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        pipe_codes = _build_lift_chain_pipes()
        pipes = [get_pipe_library().get_required_pipe(pipe_code=pipe_code) for pipe_code in pipe_codes]

        entries = build_liftable_pipes(collect_controller_taint_analyses(pipes))

        by_pipe_ref = {entry.pipe_ref: entry for entry in entries}
        assert set(by_pipe_ref.keys()) == {f"{_DOMAIN_CODE}.inv_step_a", f"{_DOMAIN_CODE}.inv_step_b"}

        step_a_entry = by_pipe_ref[f"{_DOMAIN_CODE}.inv_step_a"]
        assert step_a_entry.within_pipe_ref == f"{_DOMAIN_CODE}.inv_sequence"
        assert step_a_entry.skipped_when_absent == ["source"]
        assert "source" in step_a_entry.absence_source

        step_b_entry = by_pipe_ref[f"{_DOMAIN_CODE}.inv_step_b"]
        assert step_b_entry.skipped_when_absent == ["a_out"]

    def test_parallel_liftable_branch_is_inventoried(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        branch_found = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="inv_par_find",
            blueprint=PipeFuncBlueprint(
                description="Liftable branch",
                inputs={"source": "Text"},
                output="Text",
                function_name="optionals_inv_echo_source",
            ),
        )
        branch_base = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="inv_par_base",
            blueprint=PipeFuncBlueprint(
                description="Guaranteed branch",
                inputs={"topic": "Text"},
                output="Text",
                function_name="optionals_inv_echo_topic",
            ),
        )
        pipe_library = get_pipe_library()
        for pipe in [branch_found, branch_base]:
            pipe_library.add_new_pipe(pipe=pipe)
        parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="inv_parallel",
            blueprint=PipeParallelBlueprint(
                description="One liftable branch",
                inputs={"source": "Text?", "topic": "Text"},
                output="Composite",
                branches=[
                    SubPipeBlueprint(pipe="inv_par_find", result="found_result"),
                    SubPipeBlueprint(pipe="inv_par_base", result="base_result"),
                ],
                add_each_output=False,
            ),
        )
        pipe_library.add_new_pipe(pipe=parallel)

        entries = build_liftable_pipes(collect_controller_taint_analyses([parallel, branch_found, branch_base]))

        assert len(entries) == 1
        entry = entries[0]
        assert entry.pipe_ref == f"{_DOMAIN_CODE}.inv_par_find"
        assert entry.within_pipe_ref == f"{_DOMAIN_CODE}.inv_parallel"
        assert entry.skipped_when_absent == ["source"]

    def test_validation_report_carries_the_inventory_field(self):
        """The valid report exposes `liftable_pipes` beside `pipe_io_contracts` (empty by default)."""
        assert "liftable_pipes" in PipelexValidationReport.model_fields
