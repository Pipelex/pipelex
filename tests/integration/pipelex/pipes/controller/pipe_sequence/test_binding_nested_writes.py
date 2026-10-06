from collections.abc import Callable
from typing import TYPE_CHECKING, Any, NamedTuple

import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.interpreter_hub import get_library_manager
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.validation_error_types import PipeValidationErrorType
from tests.integration.pipelex.pipes.controller.pipe_sequence.unresolved_pipes import hide_pipe_from_sequence_analyses

if TYPE_CHECKING:
    from mthds.protocol.pipeline_inputs import PipelineInputs

_DOMAIN = "depot_stashes"

_BUNDLE_HEADER = f"""domain = "{_DOMAIN}"
description = "Stashing a parcel inside a nested controller, then reading its weight"
main_pipe = "read_stashed_weight"

[concept.Invoice]
description = "An invoice received at the depot"

[concept.Invoice.structure]
total = {{ type = "number", description = "The amount due, in euros", required = true }}

[concept.Parcel]
description = "A parcel received at the depot"

[concept.Parcel.structure]
weight = {{ type = "number", description = "The weight, in kilograms", required = true }}

[concept.Crate]
description = "A crate received at the depot"

[concept.Crate.structure]
weight = {{ type = "number", description = "The weight, in kilograms", required = true }}

[pipe.weigh_parcel]
type = "PipeCompose"
description = "Writes out a parcel of a given weight"
inputs = {{ amount = "Number" }}
output = "Parcel"

[pipe.weigh_parcel.construct]
weight = {{ from = "amount.number" }}

[pipe.weigh_crate]
type = "PipeCompose"
description = "Writes out a crate of a given weight"
inputs = {{ amount = "Number" }}
output = "Crate"

[pipe.weigh_crate.construct]
weight = {{ from = "amount.number" }}

[pipe.write_note]
type = "PipeCompose"
description = "Writes a note on what was weighed"
inputs = {{ amount = "Number" }}
output = "Text"
template = "Weighed $amount kilograms"

[pipe.describe_parcel]
type = "PipeCompose"
description = "Describes a parcel by its weight"
inputs = {{ record = "Parcel" }}
output = "Text"
template = "A parcel of {{{{ record.weight }}}} kilograms"

[pipe.stash_parcel]
type = "PipeSequence"
description = "Stores a parcel under the record's name, then writes a note"
inputs = {{ amount = "Number" }}
output = "Text"
steps = [
  {{ pipe = "weigh_parcel", result = "record" }},
  {{ pipe = "write_note", result = "note" }},
]

[pipe.stash_crate]
type = "PipeSequence"
description = "Stores a crate under the record's name, then writes a note"
inputs = {{ amount = "Number" }}
output = "Text"
steps = [
  {{ pipe = "weigh_crate", result = "record" }},
  {{ pipe = "write_note", result = "note" }},
]

[pipe.stash_handed_parcel]
type = "PipeSequence"
description = "Stores the parcel handed over, when one is, under the record's name, then writes a note"
inputs = {{ parcel = "Parcel?", amount = "Number" }}
output = "Text"
steps = [
  {{ from = "parcel", result = "record" }},
  {{ pipe = "write_note", result = "note" }},
]

[pipe.stash_by_mode]
type = "PipeCondition"
description = "Stores a parcel or a crate under the record's name, as the mode says"
inputs = {{ amount = "Number", mode = "Text" }}
output = "Text"
expression = "mode"
default_outcome = "fail"

[pipe.stash_by_mode.outcomes]
parcel = "stash_parcel"
crate = "stash_crate"

[pipe.stash_in_parallel]
type = "PipeParallel"
description = "Weighs a parcel and writes a note at once, adding each result to the memory"
inputs = {{ amount = "Number" }}
output = "Composite"
add_each_output = true
branches = [
  {{ pipe = "weigh_parcel", result = "record" }},
  {{ pipe = "write_note", result = "note" }},
]

[pipe.pick_parcel]
type = "PipeCondition"
description = "Weighs a parcel, or nothing, as the mode says"
inputs = {{ amount = "Number", mode = "Text" }}
output = "Parcel?"
expression = "mode"
default_outcome = "continue"

[pipe.pick_parcel.outcomes]
parcel = "weigh_parcel"

[pipe.stash_picked_in_parallel]
type = "PipeParallel"
description = "Picks a parcel and writes a note at once, adding each result to the memory"
inputs = {{ amount = "Number", mode = "Text" }}
output = "Composite"
add_each_output = true
branches = [
  {{ pipe = "pick_parcel", result = "record" }},
  {{ pipe = "write_note", result = "note" }},
]
"""

_READ_WEIGHT_STEP = '{ from = "record.weight", result = "weight" }'

# The calling sequence of the bundles below: a document it may be given, swapped for a parcel or left as it is by a condition,
# then a binding of its total and a plain reader of that total. The outcome storing the parcel stores the `Parcel` its pipe
# writes, which disagrees with the `Invoice` the caller may give, unless the tests hide that pipe from the sequence's analyses,
# as a pipe that does not resolve at validation (`hide_pipe_from_sequence_analyses`): the flow then cannot type the document.
_UNTYPED_ROOT_PIPES = """
[pipe.stash_doc_parcel]
type = "PipeSequence"
description = "Stores a parcel under the document's name"
inputs = { amount = "Number" }
output = "Parcel"
steps = [
  { pipe = "weigh_parcel", result = "doc" },
]

[pipe.swap_doc]
type = "PipeCondition"
description = "Swaps the document for a parcel, or leaves it, as the mode says"
inputs = { amount = "Number", mode = "Text" }
output = "Parcel?"
expression = "mode"
default_outcome = "continue"

[pipe.swap_doc.outcomes]
parcel = "stash_doc_parcel"

[pipe.write_total]
type = "PipeCompose"
description = "Writes out a total"
inputs = { total = "Number" }
output = "Text"
template = "Total: $total euros"
"""


def _bundle(*, stash_step: str, inputs: str, output: str, reading_step: str = _READ_WEIGHT_STEP) -> str:
    """The bundle with its calling sequence: a step running a nested shape that stores `record`, then a step reading it."""
    return (
        f"{_BUNDLE_HEADER}\n"
        "[pipe.read_stashed_weight]\n"
        'type = "PipeSequence"\n'
        'description = "Stashes a record inside a nested controller, then reads it"\n'
        f"inputs = {{ {inputs} }}\n"
        f'output = "{output}"\n'
        "steps = [\n"
        f"  {stash_step},\n"
        f"  {reading_step},\n"
        "]\n"
    )


def _untyped_root_bundle(*, output: str, ends_with_the_binding: bool) -> str:
    reader_step = "" if ends_with_the_binding else '  { pipe = "write_total", result = "line" },\n'
    return (
        f"{_BUNDLE_HEADER}{_UNTYPED_ROOT_PIPES}\n"
        "[pipe.read_stashed_weight]\n"
        'type = "PipeSequence"\n'
        'description = "Swaps the document or leaves it, binds its total, then writes it out"\n'
        'inputs = { doc = "Invoice?", amount = "Number", mode = "Text" }\n'
        f'output = "{output}"\n'
        "steps = [\n"
        '  { pipe = "swap_doc", result = "swapped" },\n'
        '  { from = "doc.total", result = "total" },\n'
        f"{reader_step}"
        "]\n"
    )


def _load_sequence(*, mthds_content: str, library_id: str) -> PipeSequence:
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source="stashes.mthds")
    pipes = get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])
    sequences = [pipe for pipe in pipes if isinstance(pipe, PipeSequence) and pipe.code == "read_stashed_weight"]
    assert len(sequences) == 1
    return sequences[0]


async def _run(*, mthds_content: str, inputs: "PipelineInputs") -> AbsenceRecord | float:
    """Run the bundle live, and return the weight it read, or the absence its output holds."""
    response = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(mthds_contents=[mthds_content], inputs=inputs)
    main_resolved = response.pipe_output.working_memory.resolve_main_stuff()
    if isinstance(main_resolved, AbsenceRecord):
        return main_resolved
    return response.pipe_output.main_stuff_as_number.number


class NestedShape(NamedTuple):
    """A nested shape storing `record` in the calling sequence's memory, and what each analysis must make of it."""

    stash_step: str
    inputs: str
    needed_inputs: set[str]
    # The concept the flow types `record` as when the binding of its weight reads it.
    record_concept_ref: str
    # Whether `record`, and so the binding of its weight, may hold an absence.
    is_maybe_absent: bool
    # Each run: its inputs beside the amount, and the weight it reads, `None` for an absent output.
    runs: list[tuple["PipelineInputs", float | None]]
    # Edits of the shared pipes this shape makes, each an old text and the new text replacing it.
    replacements: tuple[tuple[str, str], ...] = ()


# A parcel handed over as an input, weighing three kilograms.
_A_PARCEL: dict[str, Any] = {"concept": f"{_DOMAIN}.Parcel", "content": {"weight": 3}}

_NESTED_SHAPES = [
    pytest.param(
        NestedShape(
            stash_step='{ pipe = "stash_parcel", result = "stash_note" }',
            inputs='amount = "Number"',
            needed_inputs={"amount"},
            record_concept_ref=f"{_DOMAIN}.Parcel",
            is_maybe_absent=False,
            runs=[({}, 7.5)],
        ),
        id="a-nested-sequence",
    ),
    pytest.param(
        NestedShape(
            stash_step='{ pipe = "stash_handed_parcel", result = "stash_note" }',
            inputs='parcel = "Parcel?", amount = "Number"',
            needed_inputs={"parcel", "amount"},
            record_concept_ref=f"{_DOMAIN}.Parcel",
            is_maybe_absent=True,
            runs=[({"parcel": _A_PARCEL}, 3), ({}, None)],
        ),
        id="a-nested-sequence-storing-a-maybe-absent-value",
    ),
    pytest.param(
        NestedShape(
            stash_step='{ pipe = "stash_by_mode", result = "stash_note" }',
            inputs='amount = "Number", mode = "Text"',
            needed_inputs={"amount", "mode"},
            record_concept_ref=f"{_DOMAIN}.Parcel",
            is_maybe_absent=False,
            runs=[({"mode": "crate"}, 7.5)],
            replacements=(('crate = "stash_crate"', 'crate = "stash_parcel"'),),
        ),
        id="a-condition-whose-outcomes-agree",
    ),
    pytest.param(
        NestedShape(
            stash_step='{ pipe = "stash_by_mode", result = "stash_note" }',
            inputs='parcel = "Parcel?", amount = "Number", mode = "Text"',
            needed_inputs={"parcel", "amount", "mode"},
            record_concept_ref=f"{_DOMAIN}.Parcel",
            is_maybe_absent=True,
            runs=[({"mode": "parcel"}, 7.5), ({"mode": "crate"}, None)],
            replacements=(
                ('crate = "stash_crate"', 'crate = "stash_handed_parcel"'),
                (
                    'inputs = { amount = "Number", mode = "Text" }\noutput = "Text"',
                    'inputs = { parcel = "Parcel?", amount = "Number", mode = "Text" }\noutput = "Text"',
                ),
            ),
        ),
        id="a-condition-with-an-outcome-storing-a-maybe-absent-value",
    ),
    pytest.param(
        NestedShape(
            stash_step='{ pipe = "stash_by_mode", result = "stash_note" }',
            inputs='amount = "Number", mode = "Text", record = "Parcel"',
            needed_inputs={"amount", "mode", "record"},
            record_concept_ref=f"{_DOMAIN}.Parcel",
            is_maybe_absent=False,
            runs=[({"mode": "parcel", "record": _A_PARCEL}, 7.5), ({"mode": "crate", "record": _A_PARCEL}, 3)],
            replacements=(
                ('crate = "stash_crate"', 'crate = "continue"'),
                ('output = "Text"\nexpression = "mode"\ndefault_outcome = "fail"', 'output = "Text?"\nexpression = "mode"\ndefault_outcome = "fail"'),
            ),
        ),
        id="a-condition-with-a-continue-outcome-leaving-the-callers-value",
    ),
    pytest.param(
        NestedShape(
            stash_step='{ pipe = "stash_in_parallel", result = "stash" }',
            inputs='amount = "Number"',
            needed_inputs={"amount"},
            record_concept_ref=f"{_DOMAIN}.Parcel",
            is_maybe_absent=False,
            runs=[({}, 7.5)],
        ),
        id="a-parallel-adding-each-output",
    ),
    pytest.param(
        NestedShape(
            stash_step='{ pipe = "stash_picked_in_parallel", result = "stash" }',
            inputs='amount = "Number", mode = "Text"',
            needed_inputs={"amount", "mode"},
            record_concept_ref=f"{_DOMAIN}.Parcel",
            is_maybe_absent=True,
            runs=[({"mode": "parcel"}, 7.5), ({"mode": "none"}, None)],
        ),
        id="a-parallel-adding-a-maybe-absent-branch-result",
    ),
    pytest.param(
        NestedShape(
            stash_step='{ pipe = "stash_parcel", result = "stash_notes", batch_over = "amounts", batch_as = "amount" }',
            inputs='amounts = "Number[]", record = "Parcel"',
            needed_inputs={"amounts", "record"},
            record_concept_ref=f"{_DOMAIN}.Parcel",
            is_maybe_absent=False,
            runs=[({"record": _A_PARCEL}, 3)],
        ),
        id="a-batched-step-whose-branches-store-nothing-in-the-caller",
    ),
]


class TestBindingNestedWrites:
    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize("shape", _NESTED_SHAPES)
    async def test_the_three_analyses_agree_on_what_a_nested_shape_stores(self, load_empty_library: Callable[[], str], shape: NestedShape) -> None:
        """Needed inputs, derived type and absence agree on the name a nested shape stores, and the run does what they say."""
        mthds_content = _bundle(stash_step=shape.stash_step, inputs=shape.inputs, output="Number?" if shape.is_maybe_absent else "Number")
        for old_text, new_text in shape.replacements:
            assert old_text in mthds_content
            mthds_content = mthds_content.replace(old_text, new_text)
        sequence = _load_sequence(mthds_content=mthds_content, library_id=load_empty_library())

        assert set(sequence.needed_inputs().root) == shape.needed_inputs
        typed_flow = sequence.build_typed_flow()
        record_spec = typed_flow.final_slots["record"].stuff_spec
        assert record_spec is not None
        assert record_spec.concept.concept_ref == shape.record_concept_ref
        assert typed_flow.binding_specs[1].concept.concept_ref == "native.Number"
        assert (sequence.analyze_taint().output_taint is not None) is shape.is_maybe_absent

        for extra_inputs, expected_weight in shape.runs:
            amount_inputs: PipelineInputs = (
                {"amounts": {"concept": "native.Number", "content": [{"number": 7.5}]}}
                if "amounts" in shape.inputs
                else {"amount": {"concept": "native.Number", "content": {"number": 7.5}}}
            )
            outcome = await _run(mthds_content=mthds_content, inputs={**amount_inputs, **extra_inputs})
            if expected_weight is None:
                assert isinstance(outcome, AbsenceRecord)
            else:
                assert outcome == expected_weight

    @pytest.mark.parametrize(
        ("stash_step", "inputs"),
        [
            pytest.param('{ pipe = "stash_handed_parcel", result = "stash_note" }', 'parcel = "Parcel?", amount = "Number"', id="a-nested-sequence"),
            pytest.param('{ pipe = "stash_picked_in_parallel", result = "stash" }', 'amount = "Number", mode = "Text"', id="a-parallel"),
        ],
    )
    def test_a_nested_write_keeps_its_absence(self, load_empty_library: Callable[[], str], stash_step: str, inputs: str) -> None:
        """Regression: a nested value that may be absent makes the binding reading it maybe-absent, so a sequence ending with the
        binding declares its output `?` or is refused, rather than resolving absent behind a plain output.
        """
        mthds_content = _bundle(stash_step=stash_step, inputs=inputs, output="Number")

        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(mthds_content=mthds_content, library_id=load_empty_library())

        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert exc_info.value.pipe_code == "read_stashed_weight"
        assert "slot 'weight'" in str(exc_info.value)

    @pytest.mark.asyncio(loop_scope="class")
    @pytest.mark.parametrize(
        ("reading_step", "output", "expected_output"),
        [
            pytest.param(_READ_WEIGHT_STEP, "Number", 7.5, id="read-by-a-binding"),
            pytest.param('{ pipe = "describe_parcel", result = "description" }', "Text", "A parcel of 7.5 kilograms", id="read-by-a-pipe-step"),
        ],
    )
    async def test_a_name_a_nested_sequence_always_stores_is_no_input_of_the_caller(
        self, load_empty_library: Callable[[], str], reading_step: str, output: str, expected_output: float | str
    ) -> None:
        """Regression: a step reading a name a nested sequence always stores needs no input of that name."""
        mthds_content = _bundle(
            stash_step='{ pipe = "stash_parcel", result = "stash_note" }', inputs='amount = "Number"', output=output, reading_step=reading_step
        )

        sequence = _load_sequence(mthds_content=mthds_content, library_id=load_empty_library())

        assert set(sequence.needed_inputs().root) == {"amount"}
        response = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(
            mthds_contents=[mthds_content], inputs={"amount": {"concept": "native.Number", "content": {"number": 7.5}}}
        )
        if isinstance(expected_output, str):
            assert response.pipe_output.main_stuff_as_str == expected_output
        else:
            assert response.pipe_output.main_stuff_as_number.number == expected_output

    def test_a_name_only_some_outcomes_store_is_still_an_input_of_the_caller(self, load_empty_library: Callable[[], str]) -> None:
        """Regression: a condition with a `continue` outcome may leave the name as the caller had it, so the caller provides it."""
        mthds_content = _bundle(
            stash_step='{ pipe = "stash_by_mode", result = "stash_note" }', inputs='amount = "Number", mode = "Text"', output="Number"
        )
        mthds_content = mthds_content.replace('crate = "stash_crate"', 'crate = "continue"').replace(
            'output = "Text"\nexpression = "mode"\ndefault_outcome = "fail"', 'output = "Text?"\nexpression = "mode"\ndefault_outcome = "fail"'
        )

        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(mthds_content=mthds_content, library_id=load_empty_library())

        assert exc_info.value.error_type == PipeValidationErrorType.MISSING_INPUT_VARIABLE
        assert exc_info.value.variable_names == ["record"]
        assert "always stored by an earlier step" in str(exc_info.value)

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_lifted_nested_sequence_resolves_what_it_always_stores(self, load_empty_library: Callable[[], str]) -> None:
        """A nested sequence lifted for an absent plain input stores what it always stores as an absence, so a later step reading
        it is skipped in turn, as the absence analysis says, rather than meeting a name that holds neither a value nor an absence.
        """
        stash_step = '{ pipe = "stash_parcel", result = "stash_note" }'
        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(
                mthds_content=_bundle(stash_step=stash_step, inputs='amount = "Number?"', output="Number"), library_id=load_empty_library()
            )
        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED

        mthds_content = _bundle(stash_step=stash_step, inputs='amount = "Number?"', output="Number?")
        sequence = _load_sequence(mthds_content=mthds_content, library_id=load_empty_library())
        assert set(sequence.needed_inputs().root) == {"amount"}
        assert [liftable.pipe_ref for liftable in sequence.analyze_taint().liftable_steps] == [f"{_DOMAIN}.stash_parcel"]

        outcome = await _run(mthds_content=mthds_content, inputs={})
        assert isinstance(outcome, AbsenceRecord)
        assert outcome.kind == AbsenceKind.SKIPPED
        assert outcome.upstream is not None
        assert outcome.upstream.variable_name == "record"
        assert await _run(mthds_content=mthds_content, inputs={"amount": {"concept": "native.Number", "content": {"number": 7.5}}}) == 7.5

    def test_a_name_the_outcomes_store_under_different_concepts_is_refused(self, load_empty_library: Callable[[], str]) -> None:
        """Regression: the outcomes of a condition store `record` as a parcel or as a crate, so its concept is not known before
        the run, and the binding of its weight is refused there rather than derived when it runs.
        """
        mthds_content = _bundle(
            stash_step='{ pipe = "stash_by_mode", result = "stash_note" }', inputs='amount = "Number", mode = "Text"', output="Number"
        )

        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(mthds_content=mthds_content, library_id=load_empty_library())

        assert exc_info.value.error_type == PipeValidationErrorType.BINDING_PATH_UNRESOLVED
        assert exc_info.value.pipe_code == "read_stashed_weight"
        assert "outcome 'stash_crate' of pipe 'stash_by_mode' as 'Crate'; outcome 'stash_parcel' of pipe 'stash_by_mode' as 'Parcel'" in str(
            exc_info.value
        )

    def test_a_document_swapped_for_another_concept_is_refused(self, load_empty_library: Callable[[], str]) -> None:
        """The condition may leave the `Invoice` the caller gives or store a `Parcel`, so the binding of the document's total
        is refused before the run, whatever its output says about absence.
        """
        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(mthds_content=_untyped_root_bundle(output="Text?", ends_with_the_binding=False), library_id=load_empty_library())

        assert exc_info.value.error_type == PipeValidationErrorType.BINDING_PATH_UNRESOLVED
        assert "the concept of 'doc' is not known before the run" in str(exc_info.value)
        assert "which the step leaves when it stores nothing, as 'Invoice?'" in str(exc_info.value)

    @pytest.mark.asyncio(loop_scope="class")
    async def test_an_untyped_root_keeps_its_absence(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """Regression: a root the flow cannot type, a pipe that does not resolve at validation having stored it, still carries
        its own absence to the binding's result, so a plain reader of the result is listed as liftable and the sequence's output
        is declared `?`, as the run skips both when the root is absent.
        """
        hide_pipe_from_sequence_analyses(mocker=mocker, pipe_code="weigh_parcel")
        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(mthds_content=_untyped_root_bundle(output="Text", ends_with_the_binding=False), library_id=load_empty_library())
        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert "optional input 'doc'" in str(exc_info.value)

        mthds_content = _untyped_root_bundle(output="Text?", ends_with_the_binding=False)
        sequence = _load_sequence(mthds_content=mthds_content, library_id=load_empty_library())
        assert 1 not in sequence.build_typed_flow().binding_derivations
        taint_analysis = sequence.analyze_taint()
        assert [liftable.pipe_ref for liftable in taint_analysis.liftable_steps] == [f"{_DOMAIN}.write_total"]
        assert taint_analysis.output_taint is not None

        response = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(
            mthds_contents=[mthds_content],
            inputs={"amount": {"concept": "native.Number", "content": {"number": 7.5}}, "mode": "none"},
        )
        assert isinstance(response.pipe_output.working_memory.resolve_main_stuff(), AbsenceRecord)

    def test_an_untyped_root_ending_the_sequence_keeps_its_absence(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """Regression: a binding ending the sequence, whose root the flow cannot type, is still refused behind a plain output."""
        hide_pipe_from_sequence_analyses(mocker=mocker, pipe_code="weigh_parcel")
        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(mthds_content=_untyped_root_bundle(output="Number", ends_with_the_binding=True), library_id=load_empty_library())

        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert "optional input 'doc'" in str(exc_info.value)
