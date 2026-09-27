"""Pin: a `PipeCondition`'s own refusals are the caller's faults, and their reason reaches every surface.

The condition's expression and outcomes are the caller's own method, so when it refuses a run, the refusal
is the caller's to fix: its message names the pipe and the reason, locally and under STRICT disclosure, where
it used to be an unclassified `PipeRunError` that a validation verdict named by its title, "Pipe run", and a
hosted run answered with `An internal error occurred.`.
"""

from __future__ import annotations

from typing import Any

import pytest

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, ValidationErrorCategory
from pipelex.pipeline.exceptions import PipelineExecutionError, ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.pipeline.test_data import ConditionMethodFaultsTestData

_EMPTY_EXPRESSION_REASON = "PipeCondition 'route_parcel': Conditional expression returned no result"
_EMPTY_EXPRESSION_NEXT_STEP = (
    "Change the expression of PipeCondition 'route_parcel' so that it always renders a value: "
    "the name of one of its outcomes, or any other value, which takes the default outcome."
)
_ALL_FAIL_REASON = (
    "PipeCondition 'route_parcel' maps every outcome (and the default) to 'fail': every live run of this pipe raises. "
    "Map at least one outcome to a pipe or to 'continue'."
)


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


@pytest.mark.asyncio(loop_scope="class")
class TestConditionMethodFaults:
    @pytest.mark.parametrize(
        ("bundle", "reason"),
        [
            (_EMPTY_EXPRESSION_BUNDLE, _EMPTY_EXPRESSION_REASON),
            (_ALL_FAIL_BUNDLE, _ALL_FAIL_REASON),
        ],
        ids=["expression_renders_nothing", "every_outcome_fails"],
    )
    async def test_a_dry_run_refusal_is_an_item_with_its_reason(self, bundle: str, reason: str) -> None:
        """The verdict item names the pipe and the reason, locally and in the STRICT payload, never the title "Pipe run"."""
        verdict = await _verdict(bundle=bundle)

        (item,) = verdict.to_error_report().validation_errors or []
        assert item.category == ValidationErrorCategory.DRY_RUN
        assert item.pipe_code == "route_parcel"
        assert item.message == f"Pipe 'route_parcel' failed its dry run: {reason}"

        strict_payload = verdict.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        (strict_item,) = strict_payload["validation_errors"]
        assert strict_item["message"] == f"Pipe 'route_parcel' failed its dry run: {reason}"

    async def test_an_expression_that_renders_nothing_is_the_callers_fault_under_strict(self) -> None:
        """A run whose condition expression renders nothing: HTTP 422, the reason at the condition, and the next step."""
        error = await _failed_run(bundle=_EMPTY_EXPRESSION_BUNDLE, inputs={"parcel": "a box of books"})

        document = error.to_error_report().to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert document["status"] == 422
        assert document["error_domain"] == "input"
        assert document["error_type"] == "PipeRunError"
        assert document["detail"] == f"Pipe 'route_parcel' failed: {_EMPTY_EXPRESSION_REASON}"
        assert document["user_action"] == {"kind": "change_input", "detail": _EMPTY_EXPRESSION_NEXT_STEP}

    async def test_a_fail_outcome_is_the_callers_fault_under_strict(self) -> None:
        """A run whose lane the method maps to 'fail': HTTP 422, naming the pipe, never the value its expression rendered."""
        error = await _failed_run(bundle=_LANE_BUNDLE, inputs={"parcel": "a box of books", "lane": "reject"})

        document = error.to_error_report().to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert document["status"] == 422
        assert document["error_domain"] == "input"
        assert document["error_type"] == "PipeRunError"
        assert document["detail"] != INTERNAL_ERROR_PLACEHOLDER
        # The rendered value can be text of a condition a host library declared, so no message carries it.
        assert document["detail"] == "Pipe 'route_parcel' failed: PipeCondition 'route_parcel' failed with outcome: fail."
        assert document["user_action"] == {
            "kind": "change_input",
            "detail": (
                "PipeCondition 'route_parcel' refuses this run on purpose: change the inputs so that its expression "
                "selects another outcome, or map that outcome to a pipe or to 'continue'."
            ),
        }
