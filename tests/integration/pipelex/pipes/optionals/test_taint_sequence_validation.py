"""Static absence-taint pass over a PipeSequence's dataflow (D6): a maybe-absent slot must reach
an explicit sink (`?` input, `!` input) before the sequence boundary, or the sequence must declare
its output optional — otherwise validation fails with `OPTIONAL_NOT_HANDLED` naming the source,
the propagation path, and the fixes.
"""

from typing import Callable

import pytest

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.system.registries.func_registry import func_registry
from pipelex.validation_error_types import PipeValidationErrorType

_DOMAIN_CODE = "test_optionals_taint_seq"


def optionals_taint_echo_source(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"a:{working_memory.get_stuff_as_str(name='source')}")


def optionals_taint_echo_a_out(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"b:{working_memory.get_stuff_as_str(name='a_out')}")


def optionals_taint_sink(working_memory: WorkingMemory) -> TextContent:
    b_out_stuff = working_memory.get_optional_stuff(name="b_out")
    if b_out_stuff is None:
        return TextContent(text="no analysis")
    return TextContent(text=f"analysis: {b_out_stuff.as_text.text}")


_TEST_FUNCS = [optionals_taint_echo_source, optionals_taint_echo_a_out, optionals_taint_sink]


def _register_step_pipes(*, source_input_ref: str = "Text") -> None:
    """Register step A (consumes `source`), step B (consumes `a_out`), and the absorbing sink."""
    step_a = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="taint_step_a",
        blueprint=PipeFuncBlueprint(
            description="Consumes source",
            inputs={"source": source_input_ref},
            output="Text",
            function_name="optionals_taint_echo_source",
        ),
    )
    step_b = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="taint_step_b",
        blueprint=PipeFuncBlueprint(
            description="Consumes step A's output",
            inputs={"a_out": "Text"},
            output="Text",
            function_name="optionals_taint_echo_a_out",
        ),
    )
    sink_c = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="taint_sink_c",
        blueprint=PipeFuncBlueprint(
            description="Absorbing sink: declares b_out optional",
            inputs={"b_out": "Text?"},
            output="Text",
            function_name="optionals_taint_sink",
        ),
    )
    pipe_library = get_pipe_library()
    for pipe in [step_a, step_b, sink_c]:
        pipe_library.add_new_pipe(pipe=pipe)


def _build_sequence(*, output_ref: str, steps: list[SubPipeBlueprint], inputs: dict[str, str]) -> PipeSequence:
    sequence = PipeFactory[PipeSequence].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="taint_sequence",
        blueprint=PipeSequenceBlueprint(
            description="Taint-pass test sequence",
            inputs=inputs,
            output=output_ref,
            steps=steps,
        ),
    )
    get_pipe_library().add_new_pipe(pipe=sequence)
    return sequence


class TestSequenceTaintValidation:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    def test_taint_reaching_plain_sequence_output_is_rejected(self, load_empty_library: Callable[[], str]):
        """Optional sequence input feeds a lift chain that ends the sequence: plain output → error
        naming the source, the tainted variable, and the three fixes.
        """
        load_empty_library()
        _register_step_pipes()
        sequence = _build_sequence(
            output_ref="Text",
            inputs={"source": "Text?"},
            steps=[
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_a", result="a_out"),
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_b", result="b_out"),
            ],
        )

        with pytest.raises(PipeValidationError) as exc_info:
            sequence.validate_with_libraries()
        error = exc_info.value
        assert error.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert error.pipe_code == "taint_sequence"
        # The structured field carries the origin variable identifier, not prose.
        assert error.variable_names == ["source"]
        # The message names the absence source and the fixes.
        assert "source" in str(error)
        assert "?" in str(error)

    def test_one_count_step_result_keeps_the_taint(self, load_empty_library: Callable[[], str]):
        """`nb_output = 1` is the single form: the step's result is NOT plural, so the taint
        must reach the boundary exactly as it does with no count at all.
        """
        load_empty_library()
        _register_step_pipes()
        sequence = _build_sequence(
            output_ref="Text",
            inputs={"source": "Text?"},
            steps=[
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_a", result="a_out"),
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_b", result="b_out", nb_output=1),
            ],
        )

        with pytest.raises(PipeValidationError) as exc_info:
            sequence.validate_with_libraries()
        error = exc_info.value
        assert error.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert error.variable_names == ["source"]

    def test_plural_count_step_result_absorbs_the_taint(self, load_empty_library: Callable[[], str]):
        """A genuine list result (`nb_output = 2`) is never tainted — its "nothing" is the empty list."""
        load_empty_library()
        _register_step_pipes()
        sequence = _build_sequence(
            output_ref="Text[2]",
            inputs={"source": "Text?"},
            steps=[
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_a", result="a_out"),
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_b", result="b_out", nb_output=2),
            ],
        )
        sequence.validate_with_libraries()

    def test_optional_sequence_output_accepts_the_taint(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        _register_step_pipes()
        sequence = _build_sequence(
            output_ref="Text?",
            inputs={"source": "Text?"},
            steps=[
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_a", result="a_out"),
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_b", result="b_out"),
            ],
        )
        sequence.validate_with_libraries()

    def test_absorbing_sink_terminates_the_taint(self, load_empty_library: Callable[[], str]):
        """The `?` input on the final step sinks the chain: plain sequence output is fine."""
        load_empty_library()
        _register_step_pipes()
        sequence = _build_sequence(
            output_ref="Text",
            inputs={"source": "Text?"},
            steps=[
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_a", result="a_out"),
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_b", result="b_out"),
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_sink_c", result="final_report"),
            ],
        )
        sequence.validate_with_libraries()

    def test_force_input_terminates_the_taint(self, load_empty_library: Callable[[], str]):
        """A `!` input asserts presence at run time, so statically the taint stops there."""
        load_empty_library()
        _register_step_pipes(source_input_ref="Text!")
        sequence = _build_sequence(
            output_ref="Text",
            inputs={"source": "Text?"},
            steps=[
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_a", result="a_out"),
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_b", result="b_out"),
            ],
        )
        sequence.validate_with_libraries()

    def test_plain_inputs_produce_no_taint(self, load_empty_library: Callable[[], str]):
        load_empty_library()
        _register_step_pipes()
        sequence = _build_sequence(
            output_ref="Text",
            inputs={"source": "Text"},
            steps=[
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_a", result="a_out"),
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_b", result="b_out"),
            ],
        )
        sequence.validate_with_libraries()

    def test_continue_chain_taints_the_condition_result(self, load_empty_library: Callable[[], str]):
        """A `continue`-able condition (declared `?` output per OPTIONAL_OUTPUT_REQUIRED) taints
        its result slot; a plain consumer ending the sequence leaks it.
        """
        load_empty_library()
        _register_step_pipes()
        gate = PipeFactory[PipeCondition].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="taint_gate",
            blueprint=PipeConditionBlueprint(
                description="All-special-outcomes gate: output resolves absent on continue",
                inputs={"topic": "Text"},
                output="Text?",
                expression="topic",
                outcomes={"skip": "continue"},
                default_outcome="continue",
            ),
        )
        get_pipe_library().add_new_pipe(pipe=gate)
        sequence = _build_sequence(
            output_ref="Text",
            inputs={"topic": "Text"},
            steps=[
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_gate", result="source"),
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_a", result="a_out"),
            ],
        )

        with pytest.raises(PipeValidationError) as exc_info:
            sequence.validate_with_libraries()
        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED

    def test_batch_compaction_stops_the_taint(self, load_empty_library: Callable[[], str]):
        """A batched step over a plain list whose inner pipe declares a `?` output compacts to a
        guaranteed list (D4): no taint escapes, the plain sequence output is fine.
        """
        load_empty_library()
        finder = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="taint_item_finder",
            blueprint=PipeFuncBlueprint(
                description="Per-item finder that may find nothing",
                inputs={"item": "Text"},
                output="Text?",
                function_name="optionals_taint_echo_source",
            ),
        )
        list_sink = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="taint_list_sink",
            blueprint=PipeFuncBlueprint(
                description="Consumes the compacted list — a guaranteed slot",
                inputs={"found_items": "Text[]"},
                output="Text",
                function_name="optionals_taint_sink",
            ),
        )
        pipe_library = get_pipe_library()
        pipe_library.add_new_pipe(pipe=finder)
        pipe_library.add_new_pipe(pipe=list_sink)
        sequence = _build_sequence(
            output_ref="Text",
            inputs={"items": "Text[]"},
            steps=[
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_item_finder", result="found_items", batch_over="items", batch_as="item"),
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_list_sink", result="summary"),
            ],
        )
        sequence.validate_with_libraries()

    def test_lifted_parallel_branch_slot_is_tainted(self, load_empty_library: Callable[[], str]):
        """An add_each_output parallel writes branch result slots into the sequence flow; a
        liftable branch's slot is maybe-absent and a plain consumer ending the sequence leaks it.
        """
        load_empty_library()
        _register_step_pipes()
        branch_base = PipeFactory[PipeFunc].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="taint_par_base",
            blueprint=PipeFuncBlueprint(
                description="Guaranteed branch",
                inputs={"topic": "Text"},
                output="Text",
                function_name="optionals_taint_echo_source",
            ),
        )
        get_pipe_library().add_new_pipe(pipe=branch_base)
        parallel = PipeFactory[PipeParallel].make_from_blueprint(
            domain_code=_DOMAIN_CODE,
            pipe_code="taint_parallel",
            blueprint=PipeParallelBlueprint(
                description="Parallel with a liftable branch, each output added to the flow",
                inputs={"source": "Text?", "topic": "Text"},
                output="Composite",
                branches=[
                    SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_a", result="a_out"),
                    SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_par_base", result="base_out"),
                ],
                add_each_output=True,
            ),
        )
        get_pipe_library().add_new_pipe(pipe=parallel)
        sequence = _build_sequence(
            output_ref="Text",
            inputs={"source": "Text?", "topic": "Text"},
            steps=[
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_parallel", result="combined"),
                # Consumes the liftable branch's slot plain, and ends the sequence.
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_b", result="b_out"),
            ],
        )

        with pytest.raises(PipeValidationError) as exc_info:
            sequence.validate_with_libraries()
        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED

    def test_rewritten_slot_supersedes_the_taint(self, load_empty_library: Callable[[], str]):
        """A later step writing a guaranteed value under a tainted name clears the taint
        (the static mirror of the runtime value-supersedes-record invariant).
        """
        load_empty_library()
        _register_step_pipes()
        sequence = _build_sequence(
            output_ref="Text",
            inputs={"source": "Text?", "a_out": "Text"},
            steps=[
                # Step A consumes the optional source and writes b_out (tainted)...
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_a", result="b_out"),
                # ...then step B (consuming the guaranteed a_out) overwrites b_out with a
                # guaranteed value, so the sequence output is guaranteed.
                SubPipeBlueprint(pipe="test_optionals_taint_seq.taint_step_b", result="b_out"),
            ],
        )
        sequence.validate_with_libraries()
