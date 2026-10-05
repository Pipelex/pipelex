from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.interpreter_hub import get_library_manager
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.class_registry_access import get_class_registry
from pipelex.test_extras.mthds_corpus.resources import entries_root
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from mthds.protocol.pipeline_inputs import PipelineInputs

_REBOUND_ROOT_BUNDLE = """domain = "depot_records"
description = "A record name holding an invoice, then a parcel"

[concept.Invoice]
description = "An invoice received at the depot"

[concept.Invoice.structure]
total = { type = "number", description = "The amount due, in euros", required = true }

[concept.Parcel]
description = "A parcel received at the depot"

[concept.Parcel.structure]
weight = { type = "number", description = "The weight, in kilograms", required = true }
labels = { type = "list", item_type = "text", description = "The labels stuck on the parcel", required = true }

[pipe.weigh_parcel]
type = "PipeCompose"
description = "Writes out a parcel of a given weight"
inputs = { amount = "Number" }
output = "Parcel"

[pipe.weigh_parcel.construct]
weight = { from = "amount.number" }
labels = ["fragile"]

[pipe.write_line]
type = "PipeCompose"
description = "Writes a line for an amount and a weight"
inputs = { amount = "Number", weight = "Number" }
output = "Text"
template = "$amount euros for $weight kilograms"

[pipe.read_records]
type = "PipeSequence"
description = "Binds the total of the invoice, replaces the record by a parcel, then binds the parcel's weight"
inputs = { record = "Invoice" }
output = "Text"
steps = [
  { from = "record.total", result = "amount" },
  { pipe = "weigh_parcel", result = "record" },
  { from = "record.weight", result = "weight" },
  { from = "record.labels", result = "labels" },
  { pipe = "write_line", result = "line" },
]
"""


class DepotSlipRecord(StructuredContent):
    """A depot slip whose carrier note is required yet may be `None`, as a Python class can declare it."""

    reference: str
    carrier_note: str | None


_NULLABLE_FIELD_BUNDLE = """domain = "depot_slips"
description = "Reading the carrier's note off a depot slip"

[concept.DepotSlip]
description = "A slip handed over at the depot"
structure = "DepotSlipRecord"

[pipe.read_note]
type = "PipeSequence"
description = "Binds the carrier's note of a slip"
inputs = { slip = "DepotSlip" }
output = "Text"
steps = [
  { from = "slip.carrier_note", result = "note" },
]
"""

_DESCRIPTION_ONLY_BUNDLE = """domain = "depot_notices"
description = "Notices and bulletins posted at the depot"

[concept]
Notice = "A notice posted at the depot"

[concept.Bulletin]
description = "A bulletin posted at the depot"

[pipe.read_notice]
type = "PipeSequence"
description = "Binds the text inside a notice"
inputs = { notice = "Notice" }
output = "Text"
steps = [
  { from = "notice.text", result = "notice_text" },
]
"""


_BATCHED_STEP_BUNDLE = """domain = "depot_batches"
description = "Weighing a batch of parcels, then reading their weights"
main_pipe = "read_weights"

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

[pipe.read_weights]
type = "PipeSequence"
description = "Weighs a parcel for each amount, then binds their weights"
inputs = { amounts = "Number[]" }
output = "Number[]"
steps = [
  { pipe = "weigh_parcel", result = "parcels", batch_over = "amounts", batch_as = "amount" },
  { from = "parcels.weight", result = "weights" },
]
"""


def _load_sequence(*, mthds_content: str, library_id: str, pipe_code: str) -> PipeSequence:
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source="flow.mthds")
    pipes = get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])
    sequences = [pipe for pipe in pipes if isinstance(pipe, PipeSequence) and pipe.code == pipe_code]
    assert len(sequences) == 1
    return sequences[0]


class TestBindingTypedFlow:
    def test_the_latest_producer_types_a_root(self, load_empty_library: Callable[[], str]) -> None:
        """A name a later step stores replaces what was there, so a binding after it walks the new value's concept."""
        sequence = _load_sequence(mthds_content=_REBOUND_ROOT_BUNDLE, library_id=load_empty_library(), pipe_code="read_records")

        flow = sequence.build_typed_flow()

        assert sorted(flow.binding_derivations) == [0, 2, 3]
        assert flow.binding_specs[0].concept.concept_ref == "native.Number"
        assert flow.binding_specs[0].multiplicity is None
        assert flow.binding_specs[2].concept.concept_ref == "native.Number"
        assert flow.binding_specs[3].concept.concept_ref == "native.Text"
        assert flow.binding_specs[3].multiplicity is True
        assert sorted(flow.binding_slots_by_pipe_step[1]) == ["amount"]
        assert sorted(flow.binding_slots_by_pipe_step[4]) == ["amount", "labels", "weight"]
        assert flow.final_slots["record"].stuff_spec is not None
        assert flow.final_slots["record"].stuff_spec.concept.concept_ref == "depot_records.Parcel"

    def test_a_binding_walking_the_replaced_concept_is_refused(self, load_empty_library: Callable[[], str]) -> None:
        """The library refuses the sequence when it loads: the root was replaced by a Parcel, which has no `total`."""
        mthds_content = _REBOUND_ROOT_BUNDLE.replace('{ from = "record.weight", result = "weight" }', '{ from = "record.total", result = "weight" }')

        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(mthds_content=mthds_content, library_id=load_empty_library(), pipe_code="read_records")

        assert exc_info.value.error_type == PipeValidationErrorType.BINDING_PATH_UNRESOLVED
        assert exc_info.value.pipe_code == "read_records"
        assert "holds a 'depot_records.Parcel', which has no field 'total'. Its fields are: 'weight', 'labels'." in str(exc_info.value)

    @pytest.mark.parametrize(
        ("output", "is_refused"),
        [
            pytest.param("Text", True, id="a-plain-output-is-refused"),
            pytest.param("Text?", False, id="an-optional-output-validates"),
        ],
    )
    def test_a_required_field_that_admits_none_may_leave_the_binding_absent(
        self, load_empty_library: Callable[[], str], output: str, is_refused: bool
    ) -> None:
        """A Python class can require a field and still let it hold `None`, so a sequence ending on it must declare its output `?`."""
        library_id = load_empty_library()
        # Registered in the library just opened, whose class registry the concept's `structure` is resolved through.
        get_class_registry().register_class(DepotSlipRecord)
        mthds_content = _NULLABLE_FIELD_BUNDLE.replace('output = "Text"', f'output = "{output}"')
        if not is_refused:
            sequence = _load_sequence(mthds_content=mthds_content, library_id=library_id, pipe_code="read_note")
            assert sequence.build_typed_flow().binding_derivations[0].may_find_nothing is True
            return
        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(mthds_content=mthds_content, library_id=library_id, pipe_code="read_note")

        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert "'slip.carrier_note'" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("root_name", "concept_code"),
        [
            pytest.param("notice", "Notice", id="declared-as-a-string"),
            pytest.param("bulletin", "Bulletin", id="declared-as-a-table-with-a-description"),
        ],
    )
    def test_a_description_only_concept_is_never_entered(self, load_empty_library: Callable[[], str], root_name: str, concept_code: str) -> None:
        """Both spellings of a concept declared with a description alone are refused the same way, as having no structure."""
        mthds_content = _DESCRIPTION_ONLY_BUNDLE.replace('inputs = { notice = "Notice" }', f'inputs = {{ {root_name} = "{concept_code}" }}').replace(
            '{ from = "notice.text", result = "notice_text" }', f'{{ from = "{root_name}.text", result = "notice_text" }}'
        )

        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(mthds_content=mthds_content, library_id=load_empty_library(), pipe_code="read_notice")

        assert exc_info.value.error_type == PipeValidationErrorType.BINDING_PATH_UNRESOLVED
        assert f"'{root_name}' holds a 'depot_notices.{concept_code}', which is declared with neither a structure nor refines" in str(exc_info.value)

    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize(
        "step_count",
        [
            pytest.param("", id="a-plain-batch"),
            pytest.param(", nb_output = 1", id="a-batch-asking-for-one-output"),
            pytest.param(", nb_output = 3", id="a-batch-asking-for-three-outputs"),
            pytest.param(", multiple_output = true", id="a-batch-asking-for-multiple-outputs"),
        ],
    )
    async def test_a_batched_step_stores_a_list_whatever_count_it_asks_for(self, load_empty_library: Callable[[], str], step_count: str) -> None:
        """A batched step stores the list of its branches' results, so a binding over it is plural, as the run binds it."""
        mthds_content = _BATCHED_STEP_BUNDLE.replace('batch_as = "amount" }', f'batch_as = "amount"{step_count} }}')
        sequence = _load_sequence(mthds_content=mthds_content, library_id=load_empty_library(), pipe_code="read_weights")

        flow = sequence.build_typed_flow()

        assert flow.binding_derivations[1].multiplicity is True
        assert flow.binding_specs[1].concept.concept_ref == "native.Number"
        assert flow.binding_specs[1].multiplicity is True
        assert flow.final_slots["parcels"].stuff_spec is not None
        assert flow.final_slots["parcels"].stuff_spec.multiplicity is True

        inputs: PipelineInputs = {"amounts": {"concept": "native.Number", "content": [{"number": 2.5}, {"number": 4}]}}
        response = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(mthds_contents=[mthds_content], inputs=inputs)

        assert [item.number for item in response.pipe_output.main_stuff_as_items(item_type=NumberContent)] == [2.5, 4]

    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize(
        ("entry_name", "message_fragments"),
        [
            pytest.param(
                "invalid_binding_path_unresolved_unknown_field",
                ["has no field 'totl'", "Its fields are: 'total', 'lines', 'order_details'"],
                id="I11-names-the-available-fields",
            ),
            pytest.param(
                "invalid_binding_path_unresolved_past_a_leaf",
                ["'invoice.total'", "'amount'"],
                id="I12-past-a-leaf",
            ),
            pytest.param(
                "invalid_binding_path_unresolved_root_without_structure",
                ["'note' holds a 'native.Text', which holds its value in a single field"],
                id="I13-root-without-structure",
            ),
            pytest.param(
                "invalid_binding_path_unresolved_through_a_dict",
                ["'order_ref'", "'invoice.order_details'"],
                id="I14-through-a-dict",
            ),
            pytest.param(
                "invalid_missing_input_variable_binding_root",
                ["Declare 'invoice' in the sequence's `inputs`"],
                id="I15-root-nowhere",
            ),
            pytest.param(
                "invalid_input_stuff_spec_mismatch_binding",
                ["total_amount", "Number"],
                id="I16-consumer-mismatch",
            ),
            pytest.param(
                "invalid_inadequate_output_multiplicity_binding",
                ["page_views"],
                id="I17-plural-into-singular",
            ),
            pytest.param(
                "invalid_optional_not_handled_binding",
                ['binding step { from = "delivery_round.note", result = "note" }', "'delivery_round.note'"],
                id="I18-absence-escapes",
            ),
        ],
    )
    async def test_a_binding_refusal_names_what_to_change(self, entry_name: str, message_fragments: list[str]) -> None:
        entry_directory = entries_root() / entry_name

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_file_path=entry_directory / "bundle.mthds", library_dirs=[entry_directory])

        validation_errors = exc_info.value.to_error_report().validation_errors or []
        assert len(validation_errors) == 1
        message = validation_errors[0].message or ""
        for fragment in message_fragments:
            assert fragment in message, f"'{fragment}' not in: {message}"
