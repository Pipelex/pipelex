from typing import Any

import pytest
from pydantic import ValidationError

from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.mthds_parsing.exceptions import MthdsParserError
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.binding.binding_step_blueprint import BindingStepBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.validation_error_types import PipeValidationErrorType

_BUNDLE_HEADER = """domain = "billing"
description = "Reading the total of an invoice"

[concept.Invoice]
description = "An invoice sent by a supplier"

[concept.Invoice.structure]
total = { type = "number", description = "The amount due", required = true }

[pipe.write_receipt]
type = "PipeCompose"
description = "Writes a receipt for an amount"
inputs = { total_amount = "Number" }
output = "Text"
template = "Received $total_amount"

[pipe.acknowledge_invoice]
type = "PipeSequence"
description = "Acknowledges an invoice by its total"
inputs = { invoice = "Invoice" }
output = "Text"
"""


def _sequence_bundle(*, steps_toml: str) -> str:
    return f"{_BUNDLE_HEADER}steps = [\n{steps_toml}\n]\n"


def _parse_sequence(*, steps_toml: str) -> PipeSequenceBlueprint:
    bundle = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_sequence_bundle(steps_toml=steps_toml), mthds_source="main.mthds")
    assert bundle.pipe is not None
    sequence = bundle.pipe["acknowledge_invoice"]
    assert isinstance(sequence, PipeSequenceBlueprint)
    return sequence


class TestSequenceStepUnion:
    def test_a_step_carrying_from_parses_as_a_binding_step(self) -> None:
        sequence = _parse_sequence(
            steps_toml="""    { from = "invoice.total", result = "total_amount" },
    { pipe = "write_receipt", result = "receipt" },""",
        )

        binding_step = sequence.steps[0]
        assert isinstance(binding_step, BindingStepBlueprint)
        assert binding_step.from_path == "invoice.total"
        assert binding_step.result == "total_amount"
        assert binding_step.root_name == "invoice"
        assert isinstance(sequence.steps[1], SubPipeBlueprint)
        assert sequence.pipe_steps == [SubPipeBlueprint(pipe="write_receipt", result="receipt")]

    def test_a_binding_step_runs_no_pipe(self) -> None:
        sequence = _parse_sequence(
            steps_toml="""    { from = "invoice.total", result = "total_amount" },
    { pipe = "write_receipt", result = "receipt" },""",
        )

        assert sequence.pipe_dependencies == {"write_receipt"}
        assert sequence.ordered_pipe_dependencies == ["write_receipt"]

    @pytest.mark.parametrize(
        "dump_kwargs",
        [
            pytest.param({}, id="default"),
            pytest.param({"mode": "json"}, id="json-mode"),
            pytest.param({"by_alias": True}, id="by-alias"),
            pytest.param({"by_alias": False}, id="by-field-name"),
            pytest.param({"mode": "json", "exclude_none": True}, id="crate-emission"),
        ],
    )
    def test_a_binding_step_serializes_under_from_whatever_the_caller_asks(self, dump_kwargs: dict[str, Any]) -> None:
        """`from_path` is Python's name only: every dump writes `from`, the one key the parser reads back."""
        binding_step = BindingStepBlueprint.model_validate({"from": "invoice.total", "result": "total_amount"})

        dumped = binding_step.model_dump(**dump_kwargs)

        assert dumped == {"from": "invoice.total", "result": "total_amount"}
        assert BindingStepBlueprint.model_validate(dumped) == binding_step

    def test_a_sequence_holding_a_binding_step_dumps_and_validates_again(self) -> None:
        sequence = _parse_sequence(
            steps_toml="""    { from = "invoice.total", result = "total_amount" },
    { pipe = "write_receipt", result = "receipt" },""",
        )

        dumped = sequence.model_dump(mode="json")

        assert dumped["steps"][0] == {"from": "invoice.total", "result": "total_amount"}
        assert PipeSequenceBlueprint.model_validate(dumped) == sequence

    @pytest.mark.parametrize(
        ("step_toml", "message_fragment"),
        [
            pytest.param(
                '{ pipe = "write_receipt", from = "invoice.total", result = "total_amount" }',
                "carries both `pipe` and `from`",
                id="I6-pipe-and-from",
            ),
            pytest.param('{ from = "invoice.total" }', "a binding step without `result`", id="I7-without-result"),
            pytest.param(
                '{ from = "invoice.total", result = "total_amount", batch_over = "totals", batch_as = "total" }',
                "cannot carry `batch_over`, `batch_as`",
                id="I8-batch-fields",
            ),
            pytest.param('{ from = "invoice.lines[0]", result = "first_line" }', "is not a path", id="I9-subscript"),
            pytest.param('{ from = "invoice._total", result = "total_amount" }', "is not a path", id="I9-underscore-led-segment"),
            pytest.param('{ from = "invoice.total", result = "TotalAmount" }', "is not a plain input name", id="result-not-plain"),
            pytest.param('{ from = "invoice.total", result = "total.amount" }', "is not a plain input name", id="result-dotted"),
        ],
    )
    def test_a_malformed_binding_step_is_refused_as_binding_step_invalid(self, step_toml: str, message_fragment: str) -> None:
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_sequence_bundle(steps_toml=f"    {step_toml},"), mthds_source="main.mthds")

        errors = exc_info.value.validation_errors
        assert [error.error_type for error in errors] == [PipeValidationErrorType.BINDING_STEP_INVALID]
        assert errors[0].pipe_code == "acknowledge_invoice"
        assert message_fragment in errors[0].message

    @pytest.mark.parametrize(
        "step_toml",
        [
            pytest.param('{ from_path = "invoice.total", result = "total_amount" }', id="from-path-alone"),
            pytest.param('{ from = "invoice.total", from_path = "invoice.total", result = "total_amount" }', id="from-path-beside-from"),
        ],
    )
    def test_a_step_spelling_its_path_from_path_is_refused(self, step_toml: str) -> None:
        """`from_path` is the Python name of the field, not MTHDS: the parser refuses it, as the schema does."""
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_sequence_bundle(steps_toml=f"    {step_toml},"), mthds_source="main.mthds")

        assert "from_path" in str(exc_info.value)
        with pytest.raises(ValidationError):
            BindingStepBlueprint.model_validate({"from_path": "invoice.total", "result": "total_amount"})

    def test_i10_a_binding_step_in_a_parallel_branch_is_refused(self) -> None:
        mthds_content = f"""{_BUNDLE_HEADER}steps = [{{ pipe = "acknowledge_in_parallel", result = "receipt" }}]

[pipe.acknowledge_in_parallel]
type = "PipeParallel"
description = "Writes receipts in parallel"
inputs = {{ invoice = "Invoice" }}
output = "Text"
add_each_output = true
branches = [
    {{ from = "invoice.total", result = "total_amount" }},
]
"""
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source="main.mthds")

        errors = exc_info.value.validation_errors
        assert [error.error_type for error in errors] == [PipeValidationErrorType.BINDING_STEP_INVALID]
        assert errors[0].pipe_code == "acknowledge_in_parallel"
        assert "bind the value in a step of the calling PipeSequence, before the PipeParallel step" in errors[0].message

    def test_a_dotted_batch_over_parses_on_a_pipe_step(self) -> None:
        """The blueprint keeps the path as written: the sequence rewrites it into a binding and a batch when it loads."""
        sequence = _parse_sequence(
            steps_toml='    { pipe = "write_receipt", batch_over = "invoice.lines", batch_as = "total_amount", result = "receipts" },',
        )

        assert sequence.steps == [SubPipeBlueprint(pipe="write_receipt", batch_over="invoice.lines", batch_as="total_amount", result="receipts")]

    @pytest.mark.parametrize(
        "batch_over",
        [
            pytest.param("invoice..lines", id="an-empty-segment"),
            pytest.param("invoice.lines[0]", id="a-subscript"),
            pytest.param("invoice._lines", id="an-underscore-led-segment"),
            pytest.param("invoice.lines ", id="whitespace"),
        ],
    )
    def test_a_dotted_batch_over_outside_the_path_grammar_is_refused_as_binding_step_invalid(self, batch_over: str) -> None:
        step_toml = f'    {{ pipe = "write_receipt", batch_over = "{batch_over}", batch_as = "total_amount", result = "receipts" }},'
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_sequence_bundle(steps_toml=step_toml), mthds_source="main.mthds")

        errors = exc_info.value.validation_errors
        assert [error.error_type for error in errors] == [PipeValidationErrorType.BINDING_STEP_INVALID]
        assert errors[0].pipe_code == "acknowledge_invoice"
        assert f"the dotted `batch_over` '{batch_over}' is not a path" in errors[0].message

    @pytest.mark.parametrize(
        "batch_over",
        [
            pytest.param("invoice.lines", id="a-path"),
            pytest.param("invoice..lines", id="a-malformed-path"),
        ],
    )
    def test_a_dotted_batch_over_in_a_parallel_branch_is_refused(self, batch_over: str) -> None:
        """A dotted `batch_over` binds, and a branch never binds: the calling sequence binds the list before the parallel."""
        mthds_content = f"""{_BUNDLE_HEADER}steps = [{{ pipe = "acknowledge_in_parallel", result = "receipt" }}]

[pipe.acknowledge_in_parallel]
type = "PipeParallel"
description = "Writes receipts in parallel"
inputs = {{ invoice = "Invoice" }}
output = "Text"
add_each_output = true
branches = [
    {{ pipe = "write_receipt", batch_over = "{batch_over}", batch_as = "total_amount", result = "receipts" }},
]
"""
        with pytest.raises(MthdsParserError) as exc_info:
            MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source="main.mthds")

        errors = exc_info.value.validation_errors
        assert [error.error_type for error in errors] == [PipeValidationErrorType.BINDING_STEP_INVALID]
        assert errors[0].pipe_code == "acknowledge_in_parallel"
        assert f"Branch 1 of the parallel batches over the dotted path '{batch_over}'" in errors[0].message
        assert f'`{{ from = "{batch_over}", result = "<name>" }}`' in errors[0].message

    def test_a_parallel_branch_built_with_a_dotted_batch_over_is_refused(self) -> None:
        """A branch built in Python, not parsed from a table, is refused the same way."""
        with pytest.raises(ValidationError) as exc_info:
            PipeParallelBlueprint(
                description="Writes receipts in parallel",
                output="Composite",
                branches=[SubPipeBlueprint(pipe="write_receipt", batch_over="invoice.lines", batch_as="line", result="receipts")],
            )

        refusal = exc_info.value.errors()[0].get("ctx", {}).get("error")
        assert isinstance(refusal, PipeValidationError)
        assert refusal.error_type == PipeValidationErrorType.BINDING_STEP_INVALID

    def test_a_plain_batch_over_in_a_parallel_branch_parses(self) -> None:
        blueprint = PipeParallelBlueprint.model_validate(
            {
                "description": "Writes receipts in parallel",
                "output": "Composite",
                "branches": [{"pipe": "write_receipt", "batch_over": "lines", "batch_as": "line", "result": "receipts"}],
            }
        )

        assert blueprint.branches == [SubPipeBlueprint(pipe="write_receipt", batch_over="lines", batch_as="line", result="receipts")]

    def test_a_parallel_branch_keeps_the_pipe_step_shape(self) -> None:
        assert PipeParallelBlueprint.model_fields["branches"].annotation == list[SubPipeBlueprint]

    @pytest.mark.parametrize(
        "steps",
        [
            pytest.param(5, id="a-number"),
            pytest.param(None, id="null"),
            pytest.param("write_receipt", id="a-string"),
        ],
    )
    def test_steps_that_are_not_a_list_are_refused_as_a_list_type(self, steps: object) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PipeSequenceBlueprint.model_validate({"description": "Acknowledges an invoice", "output": "Text", "steps": steps})

        assert [error["type"] for error in exc_info.value.errors()] == ["list_type"]
        assert exc_info.value.errors()[0]["loc"] == ("steps",)

    @pytest.mark.parametrize(
        "branches",
        [
            pytest.param(None, id="null"),
            pytest.param(5, id="a-number"),
        ],
    )
    def test_branches_that_are_not_a_list_are_refused_as_a_list_type(self, branches: object) -> None:
        with pytest.raises(ValidationError) as exc_info:
            PipeParallelBlueprint.model_validate({"description": "Writes receipts in parallel", "output": "Text", "branches": branches})

        assert [error["type"] for error in exc_info.value.errors()] == ["list_type"]
        assert exc_info.value.errors()[0]["loc"] == ("branches",)
