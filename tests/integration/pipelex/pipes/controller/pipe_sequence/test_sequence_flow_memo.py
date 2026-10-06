import copy
import pickle  # ruff: ignore[suspicious-pickle-import] - the test pickles a sequence it built itself
from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from pytest_mock import MockerFixture

from pipelex.core.stuffs.number_content import NumberContent
from pipelex.interpreter_hub import get_library_manager, get_pipe_library, scoped_current_library
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.sequence import pipe_sequence as sequence_module
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode

if TYPE_CHECKING:
    from mthds.protocol.pipeline_inputs import PipelineInputs

# A sequence reading each parcel's weight through a binding step, run once per parcel by the sequence that calls it.
_WEIGHING_BUNDLE = """domain = "depot_weighing"
description = "Reading the weight of every parcel received at the depot"
main_pipe = "read_all_weights"

[concept.Parcel]
description = "A parcel received at the depot"

[concept.Parcel.structure]
weight = { type = "number", description = "The weight, in kilograms", required = true }

[pipe.weigh_parcel]
type = "PipeCompose"
description = "Writes out a parcel of a given weight"
inputs = { amount = "Number" }
output = "Parcel"

[pipe.weigh_parcel.construct]
weight = { from = "amount.number" }

[pipe.read_weight]
type = "PipeSequence"
description = "Weighs a parcel, then binds its weight"
inputs = { amount = "Number" }
output = "Number"
steps = [
  { pipe = "weigh_parcel", result = "parcel" },
  { from = "parcel.weight", result = "weight" },
]

[pipe.read_all_weights]
type = "PipeSequence"
description = "Reads the weight of a parcel for each amount"
inputs = { amounts = "Number[]" }
output = "Number[]"
steps = [
  { pipe = "read_weight", batch_over = "amounts", batch_as = "amount", result = "weights" },
]

[pipe.read_one_weight]
type = "PipeSequence"
description = "Reads the weight of one parcel through the sequence that reads it"
inputs = { amount = "Number" }
output = "Number"
steps = [
  { pipe = "read_weight", result = "weight" },
]
"""

# A pipe of the same code storing another concept, loaded into a second library beside the first library's sequence.
_OTHER_WEIGHING_BUNDLE = """domain = "depot_weighing"
description = "A depot where weighing a parcel writes out its invoice"

[concept.Invoice]
description = "An invoice for a parcel received at the depot"

[concept.Invoice.structure]
weight = { type = "number", description = "The weight billed, in kilograms", required = true }

[pipe.weigh_parcel]
type = "PipeCompose"
description = "Writes out the invoice of a parcel of a given weight"
inputs = { amount = "Number" }
output = "Invoice"

[pipe.weigh_parcel.construct]
weight = { from = "amount.number" }
"""


def _load_pipes(*, mthds_content: str, library_id: str) -> dict[str, PipeAbstract]:
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source="weighing.mthds")
    pipes = get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])
    return {pipe.code: pipe for pipe in pipes}


def _sequence(*, pipes: dict[str, PipeAbstract], pipe_code: str) -> PipeSequence:
    sequence = pipes[pipe_code]
    assert isinstance(sequence, PipeSequence)
    return sequence


def _shallow_model_copy(sequence: PipeSequence) -> PipeSequence:
    return sequence.model_copy()


def _deep_model_copy(sequence: PipeSequence) -> PipeSequence:
    return sequence.model_copy(deep=True)


def _pickled_copy(sequence: PipeSequence) -> PipeSequence:
    copied = pickle.loads(pickle.dumps(sequence))  # ruff: ignore[suspicious-pickle-usage] - a sequence this test pickled itself
    assert isinstance(copied, PipeSequence)
    return copied


class TestSequenceFlowMemo:
    def test_a_flow_is_built_once_per_state_of_the_library(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """Validating every sequence builds each flow once, and the walks that follow read it, until the library changes."""
        flow_builder_spy = mocker.spy(sequence_module, "build_sequence_typed_flow")
        pipes = _load_pipes(mthds_content=_WEIGHING_BUNDLE, library_id=load_empty_library())
        read_weight = _sequence(pipes=pipes, pipe_code="read_weight")
        read_one_weight = _sequence(pipes=pipes, pipe_code="read_one_weight")

        assert flow_builder_spy.call_count == 3

        read_weight.build_typed_flow()
        read_one_weight.needed_inputs()
        read_weight.memory_writes(visited_pipes={read_one_weight.visit_key})
        read_one_weight.analyze_taint()

        assert flow_builder_spy.call_count == 3

        get_pipe_library().remove_pipes_by_refs(pipe_refs=[pipes["read_all_weights"].pipe_ref])
        flow = read_weight.build_typed_flow()

        assert flow_builder_spy.call_count == 4
        assert flow.binding_specs[1].concept.concept_ref == "native.Number"

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_run_reads_the_flow_kept_since_validation(self, mocker: MockerFixture) -> None:
        """A sequence run once per item of a batch derives its binding from the flow its library validated, built once."""
        flow_builder_spy = mocker.spy(sequence_module, "build_sequence_typed_flow")
        inputs: PipelineInputs = {"amounts": {"concept": "native.Number", "content": [{"number": 2.5}, {"number": 4}, {"number": 7}]}}

        response = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(mthds_contents=[_WEIGHING_BUNDLE], inputs=inputs)

        assert [item.number for item in response.pipe_output.main_stuff_as_items(item_type=NumberContent)] == [2.5, 4, 7]
        assert flow_builder_spy.call_count == 3

    def test_a_flow_never_crosses_into_a_library_where_its_pipes_resolve_differently(self, load_empty_library: Callable[[], str]) -> None:
        """The same sequence, held by two libraries whose pipe of one code stores different concepts, types its flow in each."""
        first_library_id = load_empty_library()
        read_weight = _sequence(pipes=_load_pipes(mthds_content=_WEIGHING_BUNDLE, library_id=first_library_id), pipe_code="read_weight")
        parcel_spec = read_weight.build_typed_flow().final_slots["parcel"].stuff_spec
        assert parcel_spec is not None
        assert parcel_spec.concept.concept_ref == "depot_weighing.Parcel"

        library_manager = get_library_manager()
        second_library_id, second_library = library_manager.open_library()
        try:
            _load_pipes(mthds_content=_OTHER_WEIGHING_BUNDLE, library_id=second_library_id)
            second_library.pipe_library.add_new_pipe(read_weight)
            with scoped_current_library(library_id=second_library_id):
                invoice_spec = read_weight.build_typed_flow().final_slots["parcel"].stuff_spec
        finally:
            library_manager.teardown(library_id=second_library_id)

        assert invoice_spec is not None
        assert invoice_spec.concept.concept_ref == "depot_weighing.Invoice"
        parcel_spec_again = read_weight.build_typed_flow().final_slots["parcel"].stuff_spec
        assert parcel_spec_again is not None
        assert parcel_spec_again.concept.concept_ref == "depot_weighing.Parcel"

    @pytest.mark.parametrize(
        "make_copy",
        [
            pytest.param(_shallow_model_copy, id="a-shallow-copy"),
            pytest.param(_deep_model_copy, id="a-deep-copy"),
            pytest.param(copy.deepcopy, id="a-copy-module-deep-copy"),
            pytest.param(_pickled_copy, id="a-pickled-copy"),
        ],
    )
    def test_a_copy_of_a_sequence_builds_its_own_flow(
        self, load_empty_library: Callable[[], str], mocker: MockerFixture, make_copy: Callable[[PipeSequence], PipeSequence]
    ) -> None:
        """A copy may change the steps it was copied with, so it never reads the flow its original built."""
        read_weight = _sequence(pipes=_load_pipes(mthds_content=_WEIGHING_BUNDLE, library_id=load_empty_library()), pipe_code="read_weight")
        read_weight.build_typed_flow()
        flow_builder_spy = mocker.spy(sequence_module, "build_sequence_typed_flow")

        copied = make_copy(read_weight)
        copied.build_typed_flow()
        copied.build_typed_flow()
        read_weight.build_typed_flow()

        assert flow_builder_spy.call_count == 1

    def test_a_memo_never_changes_what_a_sequence_equals(self, load_empty_library: Callable[[], str]) -> None:
        """Two sequences of one definition are equal whatever each has derived, and a memo never makes a comparison recurse."""
        first_pipes = _load_pipes(mthds_content=_WEIGHING_BUNDLE, library_id=load_empty_library())
        first_read_weight = _sequence(pipes=first_pipes, pipe_code="read_weight")
        first_read_weight.build_typed_flow()
        never_validated = copy.deepcopy(first_read_weight)

        library_manager = get_library_manager()
        second_library_id, _ = library_manager.open_library()
        try:
            second_pipes = _load_pipes(mthds_content=_WEIGHING_BUNDLE, library_id=second_library_id)
            second_read_weight = _sequence(pipes=second_pipes, pipe_code="read_weight")
            with scoped_current_library(library_id=second_library_id):
                second_read_weight.build_typed_flow()
        finally:
            library_manager.teardown(library_id=second_library_id)

        assert first_read_weight is not second_read_weight
        assert first_read_weight == second_read_weight
        assert second_read_weight == first_read_weight
        assert first_read_weight == never_validated
        assert never_validated == second_read_weight
        assert first_read_weight != _sequence(pipes=first_pipes, pipe_code="read_one_weight")
        assert second_read_weight != _sequence(pipes=first_pipes, pipe_code="read_all_weights")
