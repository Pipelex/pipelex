"""Pin: a `PipeCondition`'s own refusals are the method's faults, and their sentence reaches every surface.

The condition's expression and outcomes are the caller's own method, so when it refuses a run, the refusal
is the method's to fix: the caller reads the sentence of its code, naming the pipe, and the operator its reason,
where it used to be an unclassified `PipeRunError` that a validation verdict named by its title, "Pipe run", and
a hosted run answered with `An internal error occurred.`.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain

from pipelex.base_exceptions import ValidationErrorCategory
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import PipelineExecutionError, ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.pipeline.test_data import ConditionMethodFaultsTestData

_EMPTY_EXPRESSION_REASON = "PipeCondition 'route_parcel': Conditional expression returned no result"
# The sentences the condition's refusals render for a caller, naming the pipe and no text of the expression.
_UNMATCHED_SENTENCE = "The condition of pipe 'route_parcel' rendered a value that no outcome maps."
_ALL_FAIL_SENTENCE = "The declaration at 'pipe.route_parcel.outcomes' breaks a rule of the language (every outcome and the default map to 'fail')."


def _routing_bundle(*, inputs: str, expression: str, outcomes: str, default_outcome: str) -> str:
    return (
        ConditionMethodFaultsTestData.ROUTING_MTHDS.replace(ConditionMethodFaultsTestData.INPUTS_SLOT, inputs)
        .replace(ConditionMethodFaultsTestData.EXPRESSION_SLOT, expression)
        .replace(ConditionMethodFaultsTestData.OUTCOMES_SLOT, outcomes)
        .replace(ConditionMethodFaultsTestData.DEFAULT_OUTCOME_SLOT, default_outcome)
    )


_EMPTY_EXPRESSION_BUNDLE = _routing_bundle(
    inputs=ConditionMethodFaultsTestData.PARCEL_INPUT,
    expression="''",
    outcomes=ConditionMethodFaultsTestData.LANE_OUTCOMES,
    default_outcome="send_standard",
)
_ALL_FAIL_BUNDLE = _routing_bundle(
    inputs=ConditionMethodFaultsTestData.LANE_INPUT,
    expression="lane",
    outcomes=ConditionMethodFaultsTestData.ALL_FAIL_OUTCOMES,
    default_outcome="fail",
)
_LANE_BUNDLE = _routing_bundle(
    inputs=ConditionMethodFaultsTestData.PARCEL_AND_LANE_INPUTS,
    expression="lane",
    outcomes=ConditionMethodFaultsTestData.LANE_OUTCOMES,
    default_outcome="send_standard",
)


async def _verdict(*, bundle: str) -> ValidateBundleError:
    with pytest.raises(ValidateBundleError) as exc_info:
        await validate_bundle(mthds_contents=[bundle])
    return exc_info.value


async def _failed_run(*, bundle: str, inputs: dict[str, Any]) -> PipelineExecutionError:
    with pytest.raises(PipelineExecutionError) as exc_info:
        await PipelexMTHDSProtocol().execute(pipe_code="route_parcel", mthds_contents=[bundle], inputs=inputs)
    return exc_info.value


def _assert_the_condition_s_refusal(*, error: PipelineExecutionError, code: CoreCode, domain: ProblemDomain, detail: str, message: str) -> None:
    """The caller reads the code's sentence at the condition, a 422 of its domain; the condition's own reason is the operator's."""
    caller = error.to_problem(view=ProblemView.CALLER)
    assert caller.code == code, caller.to_wire()
    assert caller.domain == domain
    assert caller.detail == detail, caller.to_wire()
    assert caller.location is not None
    assert caller.location.pipe == "route_parcel"
    assert error_code_spec(code).status == 422
    operator = error.to_problem(view=ProblemView.OPERATOR)
    assert operator.diagnostics is not None
    assert operator.diagnostics.message == message


@pytest.mark.asyncio(loop_scope="class")
class TestConditionMethodFaults:
    @pytest.mark.parametrize(
        ("bundle", "code", "sentence"),
        [
            (_EMPTY_EXPRESSION_BUNDLE, CoreCode.PIPE_CONDITION_UNMATCHED, _UNMATCHED_SENTENCE),
            (_ALL_FAIL_BUNDLE, CoreCode.METHOD_SCHEMA_VIOLATION, _ALL_FAIL_SENTENCE),
        ],
        ids=["expression_renders_nothing", "every_outcome_fails"],
    )
    async def test_a_dry_run_refusal_is_an_item_with_its_code_s_sentence(self, bundle: str, code: CoreCode, sentence: str) -> None:
        """The verdict item names the pipe and reads the sentence of the refusal's code, never the title "Pipe run"."""
        verdict = await _verdict(bundle=bundle)

        (item,) = verdict.validation_error_items() or []
        assert item.category == ValidationErrorCategory.DRY_RUN
        assert item.pipe_code == "route_parcel"
        assert item.message == f"Pipe 'route_parcel' failed its dry run: {sentence}"
        problem = verdict.to_problem(view=ProblemView.CALLER)
        (problem_item,) = problem.errors or []
        assert problem_item.code == code
        assert problem_item.detail == sentence

    async def test_an_expression_that_renders_nothing_is_the_methods_fault(self) -> None:
        """A run whose condition expression renders nothing: HTTP 422, the code's sentence at the condition."""
        error = await _failed_run(bundle=_EMPTY_EXPRESSION_BUNDLE, inputs={"parcel": "a box of books"})

        _assert_the_condition_s_refusal(
            error=error,
            code=CoreCode.PIPE_CONDITION_UNMATCHED,
            domain=ProblemDomain.METHOD,
            detail=_UNMATCHED_SENTENCE,
            message=_EMPTY_EXPRESSION_REASON,
        )

    async def test_a_fail_outcome_refuses_the_inputs(self) -> None:
        """A run whose lane the method maps to 'fail': a refusal of these inputs, naming the pipe, never the value its expression rendered."""
        error = await _failed_run(bundle=_LANE_BUNDLE, inputs={"parcel": "a box of books", "lane": "reject"})

        # The rendered value can be text of a condition a host library declared, so no reader's text carries it.
        _assert_the_condition_s_refusal(
            error=error,
            code=CoreCode.PIPE_CONDITION_REFUSED,
            domain=ProblemDomain.INPUT,
            detail="Pipe 'route_parcel' chose the outcome 'fail', which the method maps to a refusal of these inputs.",
            message="PipeCondition 'route_parcel' failed with outcome: fail.",
        )
        for view in (ProblemView.CALLER, ProblemView.OPERATOR):
            assert "reject" not in json.dumps(error.to_problem(view=view).to_wire())

    async def test_a_continue_outcome_leaves_its_rendered_value_out_of_the_absence_reason(self) -> None:
        """A step force-unwrapping a result the condition resolved to 'continue' fails naming the condition, never the value it rendered."""
        with pytest.raises(PipelineExecutionError) as exc_info:
            await PipelexMTHDSProtocol().execute(
                pipe_code="route_and_stamp",
                mthds_contents=[ConditionMethodFaultsTestData.CONTINUE_THEN_FORCE_MTHDS],
                inputs={"parcel": "a box of books", "lane": "hold"},
            )
        error = exc_info.value

        operator = error.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.error_class == "OptionalValueAbsentError"
        assert (
            "Absence origin: pipe 'route_parcel' produced no value — \"PipeCondition 'route_parcel' resolved to its 'continue' outcome\""
            in operator.diagnostics.message
        )
        caller = error.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.PIPE_FORCED_INPUT_ABSENT
        # Neither reader's text quotes the expression's rendered value.
        for text in (error.message, json.dumps(caller.to_wire()), json.dumps(operator.to_wire())):
            assert ConditionMethodFaultsTestData.HELD_LANE_LITERAL not in text
