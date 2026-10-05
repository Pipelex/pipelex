import pytest

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

    def test_a_binding_step_serializes_under_from(self) -> None:
        binding_step = BindingStepBlueprint.model_validate({"from": "invoice.total", "result": "total_amount"})

        assert binding_step.model_dump(by_alias=True) == {"from": "invoice.total", "result": "total_amount"}

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

    def test_a_parallel_branch_keeps_the_pipe_step_shape(self) -> None:
        assert PipeParallelBlueprint.model_fields["branches"].annotation == list[SubPipeBlueprint]
