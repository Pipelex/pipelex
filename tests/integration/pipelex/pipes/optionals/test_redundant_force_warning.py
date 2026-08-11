"""The useless-`!` lint (Step E): a `!` input whose slot is guaranteed present in every analyzed
flow can never fire — it surfaces as a `warnings` item on the validation report (advisory channel,
never flips `is_valid`). A `!` that asserts a maybe-absent slot in at least one flow is meaningful
and must NOT be warned about, even if another flow guarantees the slot.
"""

from typing import Callable

from pipelex.base_exceptions import ValidationErrorCategory
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationErrorType
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipeline.controller_taint import collect_controller_taint_analyses
from pipelex.pipeline.optionality_warnings import build_optionality_warnings
from pipelex.system.registries.func_registry import func_registry

_DOMAIN_CODE = "test_redundant_force"


def redundant_force_make_a(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"a:{working_memory.get_stuff_as_str(name='topic')}")


def redundant_force_consume_a(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=f"b:{working_memory.get_stuff_as_str(name='a_out')}")


_TEST_FUNCS = [redundant_force_make_a, redundant_force_consume_a]


def _build_force_pipes() -> tuple[PipeSequence, PipeSequence]:
    """Register the step pipes and build the two flows over the same `!`-consuming pipe.

    - `rf_seq_guaranteed`: a plain-input step produces `a_out` before the `!` step consumes it —
      the slot is guaranteed, the `!` is redundant in this flow.
    - `rf_seq_asserting`: the sequence declares `a_out = "Text?"` at its boundary, so the same
      `!` step asserts a maybe-absent slot — meaningful.
    """
    step_make = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="rf_step_make",
        blueprint=PipeFuncBlueprint(
            description="Always produces a_out",
            inputs={"topic": "Text"},
            output="Text",
            function_name="redundant_force_make_a",
        ),
    )
    step_force = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="rf_step_force",
        blueprint=PipeFuncBlueprint(
            description="Consumes a_out with a force marker",
            inputs={"a_out": "Text!"},
            output="Text",
            function_name="redundant_force_consume_a",
        ),
    )
    pipe_library = get_pipe_library()
    for pipe in [step_make, step_force]:
        pipe_library.add_new_pipe(pipe=pipe)

    seq_guaranteed = PipeFactory[PipeSequence].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="rf_seq_guaranteed",
        blueprint=PipeSequenceBlueprint(
            description="a_out is produced by a guaranteed step before the force consumption",
            inputs={"topic": "Text"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="test_redundant_force.rf_step_make", result="a_out"),
                SubPipeBlueprint(pipe="test_redundant_force.rf_step_force", result="final"),
            ],
        ),
    )
    seq_asserting = PipeFactory[PipeSequence].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="rf_seq_asserting",
        blueprint=PipeSequenceBlueprint(
            description="a_out is maybe-absent at the boundary; the force consumption asserts it",
            inputs={"a_out": "Text?"},
            output="Text",
            steps=[
                SubPipeBlueprint(pipe="test_redundant_force.rf_step_force", result="final"),
            ],
        ),
    )
    for sequence in [seq_guaranteed, seq_asserting]:
        pipe_library.add_new_pipe(pipe=sequence)
    return seq_guaranteed, seq_asserting


class TestRedundantForceWarning:
    @classmethod
    def setup_class(cls):
        for func in _TEST_FUNCS:
            func_registry.register_function(func)

    @classmethod
    def teardown_class(cls):
        for func in _TEST_FUNCS:
            if func_registry.has_function(func.__name__):
                func_registry.unregister_function_by_name(func.__name__)

    def test_force_on_guaranteed_slot_warns(self, load_empty_library: Callable[[], str]):
        """A `!` consumption whose slot is guaranteed in its only analyzed flow yields one warning."""
        load_empty_library()
        seq_guaranteed, _ = _build_force_pipes()

        warnings = build_optionality_warnings(collect_controller_taint_analyses([seq_guaranteed]))

        assert len(warnings) == 1
        warning = warnings[0]
        assert warning.category == ValidationErrorCategory.PIPE_VALIDATION
        assert warning.error_type == PipeValidationErrorType.OPTIONAL_FORCE_REDUNDANT
        assert warning.pipe_code == "rf_step_force"
        assert warning.domain_code == _DOMAIN_CODE
        assert warning.variable_names == ["a_out"]
        assert "a_out" in warning.message
        assert "!" in warning.message

    def test_force_asserting_a_tainted_slot_does_not_warn(self, load_empty_library: Callable[[], str]):
        """A `!` that asserts a maybe-absent slot is meaningful — no warning."""
        load_empty_library()
        _, seq_asserting = _build_force_pipes()

        assert build_optionality_warnings(collect_controller_taint_analyses([seq_asserting])) == []

    def test_meaningful_in_one_flow_silences_the_redundant_one(self, load_empty_library: Callable[[], str]):
        """The lint aggregates across flows: one asserting flow silences the redundant observation,
        so authors are never told to remove a `!` another flow relies on.
        """
        load_empty_library()
        seq_guaranteed, seq_asserting = _build_force_pipes()

        assert build_optionality_warnings(collect_controller_taint_analyses([seq_guaranteed, seq_asserting])) == []
