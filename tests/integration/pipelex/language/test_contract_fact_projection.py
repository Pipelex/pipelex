from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import pytest
from mthds.protocol.input_form import Aggregate, ChoiceOption, DocumentField, EnumField, ListField, NumberField, ObjectField, ProseField, ProseItem
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexError
from pipelex.core.concepts.choice_options import DubiousOptionReason
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.exceptions import PipeRunInputsError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import (
    clear_current_library,
    get_concept_library,
    get_current_library_id_or_none,
    get_library_manager,
    set_current_library,
)
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipeline.choice_option_warnings import build_choice_option_warnings
from pipelex.pipeline.input_form import build_input_form, qualify_current_library_crate
from pipelex.pipeline.pipe_io_contracts import build_pipe_io_contracts
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validation_errors import warning_problem_items
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from collections.abc import Callable

    from mthds.protocol.pipeline_inputs import PipelineInputs
    from pytest_mock import MockerFixture

    from pipelex.system.job_metadata import JobMetadata

_FACTS_MTHDS = """
domain = "facts_projection_test"
description = "Bundle exercising contract facts on fields and slots"

[concept.Order]
description = "A purchase order"

[concept.Order.structure]
reference = { type = "text", description = "The order reference", required = true, pattern = "^PO-[0-9]{3}$", examples = ["PO-001"] }
quantity = { type = "integer", description = "How many", required = true, minimum = 1, maximum = 99 }
buyer_email = { type = "text", description = "Where to write", format = "email" }
line_total = { type = "number", description = "The order's total", unit = "EUR", aggregate = "sum" }

[concept.Amount]
description = "An amount of money"
refines = "Number"
unit = "EUR"

[pipe.take_order]
type = "PipeLLM"
description = "Take an order"
output = "Text"
prompt = "$code $budget $order $tags $tone $price $nda $annex\\n@?mail"

[pipe.take_order.inputs]
code = { concept = "Text", description = "The customer's code", min_length = 3, max_length = 8, examples = ["ABC123"] }
budget = { concept = "Number", minimum = 0, examples = [100] }
order = "Order"
tags = { concept = "Text[]", pattern = "^[a-z]+$" }
tone = { concept = "Text", choices = [{ value = "warm", label = "Warm" }, "formal"] }
mail = { concept = "Text?", format = "email" }
price = "Amount"
nda = { concept = "Document", description = "The NDA to review" }
annex = "Document"
"""


def _teardown_validation_library(outer_library_id: str) -> None:
    validation_library_id = get_current_library_id_or_none()
    if validation_library_id is not None and validation_library_id != outer_library_id:
        set_current_library(library_id=outer_library_id)
        get_library_manager().teardown(library_id=validation_library_id)
    clear_current_library()


def _value_branch(schema: dict[str, Any], property_name: str) -> dict[str, Any]:
    value_schema: dict[str, Any] = schema["properties"][property_name]
    branches: list[dict[str, Any]] = value_schema.get("anyOf", [])
    for branch in branches:
        if branch.get("type") != "null":
            return branch
    return value_schema


@pytest.mark.asyncio(loop_scope="class")
class TestContractFactProjection:
    async def test_facts_reach_the_schema_the_descriptors_and_the_generated_class(self, load_empty_library: Callable[[], str]) -> None:
        """One bundle, every projection: the slot schema, the descriptors and the generated structure class."""
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_FACTS_MTHDS])
            io_contracts = build_pipe_io_contracts(result.pipes)
            input_form = build_input_form(result.pipes)
            pipe = next(pipe for pipe in result.pipes if pipe.code == "take_order")
            order_class = pipe.inputs.root["order"].concept
            structure_class = get_concept_library().get_structure_class(concept=order_class)
            order_schema = structure_class.model_json_schema()
            with pytest.raises(ValueError, match="should match pattern"):
                structure_class.model_validate({"reference": "nope", "quantity": 3})
            with pytest.raises(ValueError, match="less than or equal to 99"):
                structure_class.model_validate({"reference": "PO-001", "quantity": 120})
            accepted = structure_class.model_validate({"reference": "PO-001", "quantity": 3, "buyer_email": "a@example.com"})
        finally:
            _teardown_validation_library(outer_library_id)

        contract = io_contracts["facts_projection_test.take_order"]
        code_text = _value_branch(contract.inputs["code"].json_schema, "text")
        assert code_text["minLength"] == 3
        assert code_text["maxLength"] == 8
        assert code_text["examples"] == ["ABC123"]
        budget_number = _value_branch(contract.inputs["budget"].json_schema, "number")
        assert budget_number["minimum"] == 0
        assert budget_number["examples"] == [100]
        tone_text = _value_branch(contract.inputs["tone"].json_schema, "text")
        assert tone_text["enum"] == ["warm", "formal"]
        tags_schema = contract.inputs["tags"].json_schema
        assert "^[a-z]+$" in json.dumps(tags_schema)
        # The bare concept's schema stays shared and untouched: a slot without facts states none.
        assert "minLength" not in json.dumps(contract.inputs["tone"].json_schema)

        fields = {field.name: field for field in input_form["facts_projection_test.take_order"].fields}
        code_field = fields["code"]
        assert isinstance(code_field, ProseField)
        assert code_field.description == "The customer's code"
        assert (code_field.min_length, code_field.max_length, code_field.examples) == (3, 8, ["ABC123"])
        budget_field = fields["budget"]
        assert isinstance(budget_field, NumberField)
        assert (budget_field.minimum, budget_field.examples) == (0, [100])
        tone_field = fields["tone"]
        assert isinstance(tone_field, EnumField)
        assert tone_field.choices == ["warm", "formal"]
        # One option carries a word, so every option is listed, the plain one by its value alone.
        assert tone_field.options == [ChoiceOption(value="warm", label="Warm"), ChoiceOption(value="formal")]
        # A native slot's own description replaces the concept's generic definition (L-261107-df1c70); a slot declaring
        # none keeps its concept's, as the descriptor spec states.
        nda_field = fields["nda"]
        assert isinstance(nda_field, DocumentField)
        assert nda_field.description == "The NDA to review"
        annex_field = fields["annex"]
        assert isinstance(annex_field, DocumentField)
        assert annex_field.description != "The NDA to review"
        price_field = fields["price"]
        assert isinstance(price_field, NumberField)
        assert price_field.unit == "EUR"
        order_field = fields["order"]
        assert isinstance(order_field, ObjectField)
        line_total = next(field for field in order_field.fields if field.name == "line_total")
        assert isinstance(line_total, NumberField)
        assert (line_total.unit, line_total.aggregate) == ("EUR", Aggregate.SUM)
        tags_field = fields["tags"]
        assert isinstance(tags_field, ListField)
        assert isinstance(tags_field.item, ProseItem)
        assert tags_field.item.pattern == "^[a-z]+$"

        reference_schema = order_schema["properties"]["reference"]
        assert reference_schema["pattern"] == "^PO-[0-9]{3}$"
        assert reference_schema["examples"] == ["PO-001"]
        assert order_schema["properties"]["quantity"]["minimum"] == 1
        assert accepted.model_dump()["quantity"] == 3

    @pytest.mark.parametrize(
        ("inputs", "refusal"),
        [
            ({"code": "AB", "budget": 5, "tone": "warm"}, "fewer than 3 characters"),
            ({"code": "ABC", "budget": -1, "tone": "warm"}, "below the minimum 0"),
            ({"code": "ABC", "budget": 5, "tone": "shouty"}, "not one of the options"),
            ({"code": "ABC", "budget": 5, "tone": "warm", "tags": ["fine", "NOT"]}, "does not match the pattern"),
            ({"code": "ABC", "budget": 5, "tone": "warm", "mail": "not-an-email"}, "not well-formed as email"),
            ({"code": "ABC", "budget": 5, "tone": "formal", "tags": ["fine"], "mail": "a@example.com"}, None),
        ],
    )
    async def test_the_input_gate_enforces_slot_constraints(
        self, load_empty_library: Callable[[], str], job_metadata: JobMetadata, inputs: dict[str, Any], refusal: str | None
    ) -> None:
        """A caller's value breaking its slot's facts or options is `input.invalid`; a value honouring them passes."""
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_FACTS_MTHDS])
            pipe = next(pipe for pipe in result.pipes if pipe.code == "take_order")
            working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(
                cast("PipelineInputs", inputs), concept_provider=get_concept_library(), input_specs=pipe.inputs, read_scope=None
            )
            run_params = PipeRunParamsFactory.make_run_params()
            if refusal is None:
                await pipe.ensure_inputs_honour_their_contracts(working_memory=working_memory, pipe_run_params=run_params, job_metadata=job_metadata)
            else:
                with pytest.raises(PipeRunInputsError, match=refusal) as exc_info:
                    await pipe.ensure_inputs_honour_their_contracts(
                        working_memory=working_memory, pipe_run_params=run_params, job_metadata=job_metadata
                    )
                assert exc_info.value.resolve_error_code() == CoreCode.INPUT_INVALID
        finally:
            _teardown_validation_library(outer_library_id)

    @pytest.mark.parametrize(
        ("slot", "stored_text", "is_list", "refusal"),
        [
            pytest.param("code", "AB", False, "fewer than 3 characters", id="length"),
            pytest.param("tone", "shouty", False, "not one of the options", id="choices"),
            pytest.param("tags", "NOT", True, "does not match the pattern", id="pattern-on-an-item"),
            pytest.param("mail", "not-an-email", False, "not well-formed as email", id="format"),
            pytest.param("code", "ABC", False, None, id="honoured"),
        ],
    )
    async def test_the_input_gate_reads_a_text_given_by_url(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
        job_metadata: JobMetadata,
        slot: str,
        stored_text: str,
        is_list: bool,
        refusal: str | None,
    ) -> None:
        """A text the caller gave by URL is loaded through the leaf and checked as its real value, never skipped."""
        content_generator = mocker.MagicMock()
        content_generator.load_stored_texts = mocker.AsyncMock(return_value=[stored_text])
        mocker.patch("pipelex.kernel.stored_value_ops.get_content_generator", return_value=content_generator)
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_FACTS_MTHDS])
            pipe = next(pipe for pipe in result.pipes if pipe.code == "take_order")
            reference = TextContent.model_validate({"url": _STORED_URL, "size": len(stored_text), "mime_type": "text/plain", "preview": ""})
            content: Any = ListContent[TextContent](items=[TextContent(text="fine"), reference]) if is_list else reference
            stuff = StuffFactory.make_stuff(concept=pipe.inputs.root[slot].concept, content=content, name=slot)
            working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=[stuff], main_name=slot)
            run_params = PipeRunParamsFactory.make_run_params()
            if refusal is None:
                await pipe.ensure_inputs_honour_their_contracts(working_memory=working_memory, pipe_run_params=run_params, job_metadata=job_metadata)
            else:
                with pytest.raises(PipeRunInputsError, match=refusal) as exc_info:
                    await pipe.ensure_inputs_honour_their_contracts(
                        working_memory=working_memory, pipe_run_params=run_params, job_metadata=job_metadata
                    )
                assert exc_info.value.resolve_error_code() == CoreCode.INPUT_INVALID
        finally:
            _teardown_validation_library(outer_library_id)
        content_generator.load_stored_texts.assert_awaited_once()
        uri_references = content_generator.load_stored_texts.call_args.kwargs["uri_references"]
        assert [uri_reference.uri for uri_reference in uri_references] == [_STORED_URL]

    @pytest.mark.parametrize(
        ("stored_text", "refusal"),
        [
            pytest.param("ABCDEFGHIJ", "more than 8 characters", id="too-long"),
            pytest.param("ABCDEF", None, id="honoured"),
        ],
    )
    async def test_the_input_gate_reads_a_large_text_the_normalizer_stored(
        self, mocker: MockerFixture, load_empty_library: Callable[[], str], job_metadata: JobMetadata, stored_text: str, refusal: str | None
    ) -> None:
        """A text past the inline threshold is stored before the gate, and the gate still checks the text it holds."""
        load_spy = mocker.patch("pipelex.kernel.stored_value_ops.get_content_generator")
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_FACTS_MTHDS])
            pipe = next(pipe for pipe in result.pipes if pipe.code == "take_order")
            content = TextContent(text=stored_text)
            content.accept_storage(url=_STORED_URL, size=len(stored_text), mime_type="text/plain", preview="")
            assert content.is_stored
            stuff = StuffFactory.make_stuff(concept=pipe.inputs.root["code"].concept, content=content, name="code")
            working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=[stuff], main_name="code")
            run_params = PipeRunParamsFactory.make_run_params()
            if refusal is None:
                await pipe.ensure_inputs_honour_their_contracts(working_memory=working_memory, pipe_run_params=run_params, job_metadata=job_metadata)
            else:
                with pytest.raises(PipeRunInputsError, match=refusal):
                    await pipe.ensure_inputs_honour_their_contracts(
                        working_memory=working_memory, pipe_run_params=run_params, job_metadata=job_metadata
                    )
        finally:
            _teardown_validation_library(outer_library_id)
        # The value was kept loaded when it was stored, so nothing is dispatched to read it again.
        load_spy.assert_not_called()

    async def test_the_input_gate_refuses_a_stored_text_it_cannot_read(
        self, mocker: MockerFixture, load_empty_library: Callable[[], str], job_metadata: JobMetadata
    ) -> None:
        """A stored value the gate cannot read is refused, never let through unchecked."""
        mocker.patch("pipelex.pipe_operators.pipe_operator.load_stored_values_through_leaf", return_value=0)
        outer_library_id = load_empty_library()
        try:
            result = await validate_bundle(mthds_contents=[_FACTS_MTHDS])
            pipe = next(pipe for pipe in result.pipes if pipe.code == "take_order")
            reference = TextContent.model_validate({"url": _STORED_URL, "size": 3, "mime_type": "text/plain", "preview": ""})
            stuff = StuffFactory.make_stuff(concept=pipe.inputs.root["tone"].concept, content=reference, name="tone")
            working_memory = WorkingMemoryFactory.make_from_multiple_stuffs(stuff_list=[stuff], main_name="tone")
            with pytest.raises(PipeRunInputsError, match="could not be read") as exc_info:
                await pipe.ensure_inputs_honour_their_contracts(
                    working_memory=working_memory, pipe_run_params=PipeRunParamsFactory.make_run_params(), job_metadata=job_metadata
                )
            assert exc_info.value.resolve_error_code() == CoreCode.INPUT_INVALID
        finally:
            _teardown_validation_library(outer_library_id)

    async def test_a_misplaced_fact_is_refused_as_contract_fact_invalid(self, load_empty_library: Callable[[], str]) -> None:
        """A fact its site's value class rules out is refused under the standard's code, with its fact, reason and site."""
        outer_library_id = load_empty_library()
        try:
            with pytest.raises(PipelexError) as exc_info:
                await validate_bundle(mthds_contents=[_MISPLACED_FACT_MTHDS])
        finally:
            _teardown_validation_library(outer_library_id)
        problem = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert problem.code == CoreCode.METHOD_INVALID
        assert [(item.code, item.params.as_wire() if item.params is not None else None) for item in problem.errors or []] == [
            (
                CoreCode.METHOD_CONTRACT_FACT_INVALID,
                {"fact": "unit", "reason": "inapplicable", "field_path": "concept.Parcel.structure.label"},
            )
        ]

    async def test_dubious_string_options_warn_without_refusing(self, load_empty_library: Callable[[], str]) -> None:
        """An empty or repeated plain option is a warning carrying its site and reason; the bundle stays valid."""
        outer_library_id = load_empty_library()
        try:
            await validate_bundle(mthds_contents=[_DUBIOUS_MTHDS])
            warnings = build_choice_option_warnings(qualified=qualify_current_library_crate())
        finally:
            _teardown_validation_library(outer_library_id)
        assert [(warning.error_type, warning.params) for warning in warnings] == [
            (
                PipeValidationErrorType.CHOICE_OPTION_DUBIOUS,
                {"field_path": "concept.Ticket.structure.tier", "reason": DubiousOptionReason.DUPLICATE_VALUE},
            ),
            (
                PipeValidationErrorType.CHOICE_OPTION_DUBIOUS,
                {"field_path": "pipe.triage.inputs.tone", "reason": DubiousOptionReason.EMPTY_VALUE},
            ),
        ]
        assert [item.code for item in warning_problem_items(warnings=warnings)] == [CoreCode.METHOD_CHOICE_OPTION_DUBIOUS] * 2


_STORED_URL = "pipelex-storage://facts-test/inputs/value.txt"

_MISPLACED_FACT_MTHDS = """
domain = "misplaced_fact_test"
description = "Bundle putting a unit on a text field"

[concept.Parcel]
description = "A parcel"

[concept.Parcel.structure]
label = { type = "text", description = "The label", unit = "kg" }
"""

_DUBIOUS_MTHDS = """
domain = "dubious_options_test"
description = "Bundle with dubious plain options"

[concept.Ticket]
description = "A support ticket"

[concept.Ticket.structure]
tier = { description = "The tier", choices = ["gold", "gold", "silver"], required = true }

[pipe.triage]
type = "PipeLLM"
description = "Triage the ticket"
inputs = { tone = { concept = "Text", choices = ["", "warm"] } }
output = "Ticket"
prompt = "Triage in a $tone tone"
"""
