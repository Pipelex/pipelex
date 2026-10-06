from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.interpreter_hub import get_library_manager
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.validation_error_types import PipeValidationErrorType
from tests.integration.pipelex.pipes.controller.pipe_sequence.unresolved_pipes import hide_pipe_from_sequence_analyses

# The pipes every case's sequence reads from: each case appends one sequence, `flow`, whose steps hand values between them.
_DEPOT_PIPES = """domain = "depot_steps"
description = "The steps of a depot's sequences, each reading what an earlier step stored"

[concept.Parcel]
description = "A parcel received at the depot"

[concept.Parcel.structure]
weight = { type = "number", description = "The weight, in kilograms", required = true }

[concept.FragileParcel]
description = "A parcel the depot handles with care"
refines = "Parcel"

[concept.Invoice]
description = "An invoice received at the depot"

[concept.Invoice.structure]
total = { type = "number", description = "The amount due, in euros", required = true }

[pipe.weigh_parcel]
type = "PipeCompose"
description = "Writes out a parcel of a given weight"
inputs = { amount = "Number" }
output = "Parcel"

[pipe.weigh_parcel.construct]
weight = { from = "amount.number" }

[pipe.pack_fragile_parcel]
type = "PipeCompose"
description = "Writes out a fragile parcel of a given weight"
inputs = { amount = "Number" }
output = "FragileParcel"

[pipe.pack_fragile_parcel.construct]
weight = { from = "amount.number" }

[pipe.make_invoice]
type = "PipeCompose"
description = "Writes out an invoice for an amount"
inputs = { amount = "Number" }
output = "Invoice"

[pipe.make_invoice.construct]
total = { from = "amount.number" }

[pipe.label_parcel]
type = "PipeCompose"
description = "Writes the label of a parcel"
inputs = { parcel = "Parcel" }
output = "Text"
template = "Parcel of $parcel.weight kilograms"

[pipe.label_record]
type = "PipeCompose"
description = "Writes the label of the parcel on record"
inputs = { record = "Parcel" }
output = "Text"
template = "Parcel of $record.weight kilograms"

[pipe.list_parcels]
type = "PipeCompose"
description = "Writes the manifest of several parcels"
inputs = { parcels = "Parcel[]" }
output = "Text"
template = "Manifest: $parcels"

[pipe.settle_invoice]
type = "PipeCompose"
description = "Writes the settlement of the invoice on record"
inputs = { record = "Invoice" }
output = "Text"
template = "Settled: $record.total euros"

[pipe.describe_amount]
type = "PipeCompose"
description = "Writes out an amount given in words"
inputs = { amount = "Text" }
output = "Text"
template = "Amount: $amount"

[pipe.note_anything]
type = "PipeCompose"
description = "Writes a note about whatever is on record"
inputs = { record = "Anything" }
output = "Text"
template = "On record: $record"

[pipe.swap_for_parcel]
type = "PipeSequence"
description = "Stores a parcel under the record's name"
inputs = { amount = "Number" }
output = "Parcel"
steps = [
  { pipe = "weigh_parcel", result = "record" },
]

[pipe.swap_for_invoice]
type = "PipeSequence"
description = "Stores an invoice under the record's name"
inputs = { amount = "Number" }
output = "Invoice"
steps = [
  { pipe = "make_invoice", result = "record" },
]

[pipe.swap_record]
type = "PipeCondition"
description = "Stores a parcel or an invoice under the record's name, as the mode says"
inputs = { amount = "Number", mode = "Text" }
output = "Anything"
expression = "mode"
default_outcome = "fail"

[pipe.swap_record.outcomes]
parcel = "swap_for_parcel"
invoice = "swap_for_invoice"
"""


def _flow(*, inputs: str, output: str, steps: list[str]) -> str:
    """The sequence `flow`, declaring `inputs` (a TOML inline table's content) and running `steps` in order."""
    step_lines = "".join(f"  {step},\n" for step in steps)
    return (
        "\n[pipe.flow]\n"
        'type = "PipeSequence"\n'
        'description = "Hands values from step to step"\n'
        f"inputs = {{ {inputs} }}\n"
        f'output = "{output}"\n'
        f"steps = [\n{step_lines}]\n"
    )


def _load_flow(*, flow: str, library_id: str) -> PipeSequence:
    """Load the depot's pipes and `flow` into the library, which validates every pipe, and return `flow`."""
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_DEPOT_PIPES + flow, mthds_source="depot.mthds")
    pipes = get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])
    sequences = [pipe for pipe in pipes if isinstance(pipe, PipeSequence) and pipe.code == "flow"]
    assert len(sequences) == 1
    return sequences[0]


class TestInterStepConceptCheck:
    @pytest.mark.parametrize(
        ("flow", "message"),
        [
            pytest.param(
                _flow(
                    inputs='amount = "Number"',
                    output="Text",
                    steps=['{ pipe = "weigh_parcel", result = "record" }', '{ pipe = "settle_invoice", result = "note" }'],
                ),
                (
                    "In pipe 'flow', step 2 (pipe 'settle_invoice') reads 'record' as 'Invoice', but step 1 (pipe 'weigh_parcel') stores it "
                    "as 'Parcel'. Declare the input as 'Parcel' in pipe 'settle_invoice', or make step 1 (pipe 'weigh_parcel') store a "
                    "'Invoice' under 'record'."
                ),
                id="a-concept-another-step-stores",
            ),
            pytest.param(
                _flow(
                    inputs='amount = "Number"',
                    output="Text",
                    steps=['{ pipe = "weigh_parcel", result = "parcels" }', '{ pipe = "list_parcels", result = "manifest" }'],
                ),
                "In pipe 'flow', step 2 (pipe 'list_parcels') reads 'parcels' as 'Parcel[]', but step 1 (pipe 'weigh_parcel') stores it as 'Parcel'.",
                id="a-list-read-where-a-single-value-is-stored",
            ),
            pytest.param(
                _flow(
                    inputs='amounts = "Number[]"',
                    output="Text",
                    steps=[
                        '{ pipe = "weigh_parcel", batch_over = "amounts", batch_as = "amount", result = "parcel" }',
                        '{ pipe = "label_parcel", result = "label" }',
                    ],
                ),
                "In pipe 'flow', step 2 (pipe 'label_parcel') reads 'parcel' as 'Parcel', but step 1 (pipe 'weigh_parcel') stores it as 'Parcel[]'.",
                id="a-single-value-read-where-a-batch-stores-a-list",
            ),
            pytest.param(
                # The last step reading `amount` sets what the sequence's inputs are checked against, so only the check of each
                # step against the flow sees the first one.
                _flow(
                    inputs='amount = "Number"',
                    output="Text",
                    steps=[
                        '{ pipe = "describe_amount", result = "note" }',
                        '{ pipe = "weigh_parcel", result = "parcel" }',
                        '{ pipe = "label_parcel", result = "label" }',
                    ],
                ),
                (
                    "In pipe 'flow', step 1 (pipe 'describe_amount') reads 'amount' as 'Text', but the sequence declares it as 'Number'. "
                    "Declare the input as 'Number' in pipe 'describe_amount', or declare 'amount' as 'Text' in the inputs of pipe 'flow'."
                ),
                id="a-declared-input-read-as-another-concept",
            ),
            pytest.param(
                _flow(
                    inputs='amount = "Number"',
                    output="Text[]",
                    steps=[
                        '{ pipe = "weigh_parcel", result = "parcels" }',
                        '{ pipe = "label_parcel", batch_over = "parcels", batch_as = "parcel", result = "labels" }',
                    ],
                ),
                (
                    "In pipe 'flow', step 2 (pipe 'label_parcel') batches over 'parcels', which step 1 (pipe 'weigh_parcel') stores as a "
                    "single 'Parcel', not a list: a batch runs its pipe once per item of a list. Batch over a name holding a list, or run "
                    "the step on the value itself, without `batch_over`."
                ),
                id="a-batch-over-a-single-value",
            ),
            pytest.param(
                _flow(
                    inputs='amounts = "Number[]"',
                    output="Text[]",
                    steps=[
                        '{ pipe = "weigh_parcel", batch_over = "amounts", batch_as = "amount", result = "parcels" }',
                        '{ pipe = "settle_invoice", batch_over = "parcels", batch_as = "record", result = "settlements" }',
                    ],
                ),
                (
                    "In pipe 'flow', step 2 (pipe 'settle_invoice') batches over 'parcels', which step 1 (pipe 'weigh_parcel') stores "
                    "as 'Parcel[]', but its pipe reads each item, 'record', as 'Invoice'. Declare 'record' as 'Parcel' in pipe "
                    "'settle_invoice', or batch over a list of 'Invoice'."
                ),
                id="a-batch-whose-items-are-read-as-another-concept",
            ),
            pytest.param(
                _flow(
                    inputs='amount = "Number", mode = "Text"',
                    output="Text",
                    steps=['{ pipe = "swap_record", result = "swapped" }', '{ pipe = "label_record", result = "label" }'],
                ),
                (
                    "In pipe 'flow', step 2 (pipe 'label_record') reads 'record' as 'Parcel', but the values 'record' may hold have different "
                    "specs: outcome 'swap_for_invoice' of pipe 'swap_record' as 'Invoice'; outcome 'swap_for_parcel' of pipe 'swap_record' "
                    "as 'Parcel'."
                ),
                id="a-name-the-outcomes-of-a-condition-store-under-different-concepts",
            ),
        ],
    )
    def test_a_step_reading_what_the_flow_does_not_carry_is_refused(self, load_empty_library: Callable[[], str], flow: str, message: str) -> None:
        """A step whose pipe reads a name as a concept or a multiplicity the flow does not carry there is refused at validation."""
        with pytest.raises(PipeValidationError) as exc_info:
            _load_flow(flow=flow, library_id=load_empty_library())

        assert exc_info.value.error_type == PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH
        assert exc_info.value.pipe_code == "flow"
        assert message in str(exc_info.value)

    @pytest.mark.parametrize(
        "flow",
        [
            pytest.param(
                _flow(
                    inputs='amount = "Number"',
                    output="Text",
                    steps=['{ pipe = "pack_fragile_parcel", result = "parcel" }', '{ pipe = "label_parcel", result = "label" }'],
                ),
                id="a-refinement-read-as-its-parent",
            ),
            pytest.param(
                _flow(
                    inputs='amounts = "Number[]"',
                    output="Text",
                    steps=[
                        '{ pipe = "weigh_parcel", batch_over = "amounts", batch_as = "amount", result = "parcels" }',
                        '{ pipe = "list_parcels", result = "manifest" }',
                    ],
                ),
                id="a-batched-result-read-as-a-list",
            ),
            pytest.param(
                _flow(
                    inputs='amounts = "Number[]"',
                    output="Text",
                    steps=[
                        '{ pipe = "weigh_parcel", batch_over = "amounts", batch_as = "amount", result = "parcels", nb_output = 1 }',
                        '{ pipe = "list_parcels", result = "manifest" }',
                    ],
                ),
                id="a-batched-result-asking-for-one-output-read-as-a-list",
            ),
            pytest.param(
                _flow(
                    inputs='amounts = "Number[]"',
                    output="Text",
                    steps=[
                        '{ pipe = "weigh_parcel", batch_over = "amounts", batch_as = "amount", result = "parcels" }',
                        '{ pipe = "pack_fragile_parcel", batch_over = "amounts", batch_as = "amount", result = "fragile_parcels" }',
                        '{ pipe = "label_parcel", batch_over = "fragile_parcels", batch_as = "parcel", result = "labels" }',
                        '{ pipe = "list_parcels", result = "manifest" }',
                    ],
                ),
                id="a-batch-over-a-list-of-refinements",
            ),
            pytest.param(
                _flow(
                    inputs='amount = "Number"',
                    output="Text",
                    steps=['{ pipe = "weigh_parcel", result = "record" }', '{ pipe = "note_anything", result = "note" }'],
                ),
                id="a-name-read-as-anything",
            ),
            pytest.param(
                _flow(
                    inputs='record = "Invoice", amount = "Number"',
                    output="Text",
                    steps=[
                        '{ pipe = "settle_invoice", result = "settlement" }',
                        '{ pipe = "weigh_parcel", result = "record" }',
                        '{ pipe = "label_record", result = "label" }',
                    ],
                ),
                id="a-declared-input-replaced-by-what-a-step-stores",
            ),
        ],
    )
    def test_a_step_reading_what_the_flow_carries_validates(self, load_empty_library: Callable[[], str], flow: str) -> None:
        """A refined concept satisfies a step reading its parent, and a batched step always stores a list."""
        sequence = _load_flow(flow=flow, library_id=load_empty_library())

        assert sequence.code == "flow"

    def test_a_name_an_unresolved_pipe_stores_is_assumed_to_deliver(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """A pipe that does not resolve at validation, as a dependency not loaded yet, gives the flow nothing to check a reader
        against, so the step reading what it stores is assumed to get what it reads, as every other check of the sequence assumes.
        """
        hide_pipe_from_sequence_analyses(mocker=mocker, pipe_code="weigh_parcel")
        flow = _flow(
            inputs='amount = "Number"',
            output="Text",
            steps=['{ pipe = "weigh_parcel", result = "record" }', '{ pipe = "settle_invoice", result = "note" }'],
        )

        sequence = _load_flow(flow=flow, library_id=load_empty_library())

        record_slot = sequence.build_typed_flow().slots_by_pipe_step[1]["record"]
        assert record_slot.stuff_spec is None
        assert record_slot.disagreement is None
        assert record_slot.producer_step_index == 0
