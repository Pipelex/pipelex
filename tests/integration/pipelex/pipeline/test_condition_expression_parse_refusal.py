"""Pin: a `PipeCondition` whose expression does not parse is refused as an item of the bundle's verdict.

The expression is the method author's own, so the refusal is the caller's to fix: validation answers an invalid
verdict with one item on the condition, saying its expression does not parse and at which line, and a run of the
bundle answers with the same verdict, which a hosted run serves as HTTP 422. Before, the parser's own error
escaped the load, so validation gave no verdict and a hosted run answered 500 "An internal error occurred.".

The item quotes neither the expression nor the parser's diagnosis, which names the token it stopped at: the
verdict is the caller's to read. A condition declared in a host's library directories is no verdict at all but
the deployment's fault, whose text is the operator's diagnostics alone.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode, StepKind

from pipelex.base_exceptions import ValidationErrorCategory, ValidationErrorItem
from pipelex.errors.error_codes import error_code_spec
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import HostLibraryLoadRefusalError, ValidateBundleError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_bundle import validate_bundle
from tests.integration.pipelex.pipeline.test_data import ConditionExpressionParseTestData, ConditionMethodFaultsTestData


def _routing_bundle(*, expression: str) -> str:
    return (
        ConditionMethodFaultsTestData.ROUTING_MTHDS.replace(
            ConditionMethodFaultsTestData.INPUTS_SLOT, ConditionMethodFaultsTestData.PARCEL_AND_LANE_INPUTS
        )
        .replace(ConditionMethodFaultsTestData.EXPRESSION_SLOT, expression)
        .replace(ConditionMethodFaultsTestData.OUTCOMES_SLOT, ConditionMethodFaultsTestData.LANE_OUTCOMES)
        .replace(ConditionMethodFaultsTestData.DEFAULT_OUTCOME_SLOT, "send_standard")
    )


# A dangling operator, and a tag where an expression is expected: neither parses at the one line of the expression.
_DANGLING_OPERATOR_BUNDLE = _routing_bundle(expression="lane ==")
_TAG_INSIDE_EXPRESSION_BUNDLE = _routing_bundle(expression="{% if %}")
# A filter that does not exist: the expression parses, but the run could not compile it.
_UNKNOWN_FILTER_BUNDLE = _routing_bundle(expression="lane.text | lenght_of_lane")

_EXPRESSION_REASON = (
    "Validation error at 'pipe.route_parcel': The 'expression' of this PipeCondition does not parse at line 1 of that expression. "
    "Fix it so that it parses as a Jinja2 expression."
)
_TEMPLATE_REASON = (
    "Validation error at 'pipe.route_parcel': The 'expression_template' of this PipeCondition does not parse at line 2 of that expression. "
    "Fix it so that it parses as a Jinja2 template."
)
_COMPILE_REASON = (
    "Validation error at 'pipe.route_parcel': The 'expression' of this PipeCondition does not compile at line 1 of that expression. "
    "Check that every filter and test it names exists, and fix it so that it compiles as a Jinja2 expression."
)

_CASES = pytest.mark.parametrize(
    ("bundle", "reason", "expression_text"),
    [
        (_DANGLING_OPERATOR_BUNDLE, _EXPRESSION_REASON, "lane =="),
        (_TAG_INSIDE_EXPRESSION_BUNDLE, _EXPRESSION_REASON, "{% if %}"),
        (ConditionExpressionParseTestData.UNKNOWN_TAG_TEMPLATE_MTHDS, _TEMPLATE_REASON, "frobnicate_the_parcel"),
        (_UNKNOWN_FILTER_BUNDLE, _COMPILE_REASON, "lenght_of_lane"),
    ],
    ids=["dangling_operator", "tag_inside_expression", "unknown_tag_on_line_2", "unknown_filter"],
)


def _assert_is_the_refusal(*, item: ValidationErrorItem, reason: str, expression_text: str) -> None:
    assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
    assert item.pipe_code == "route_parcel"
    assert item.domain_code == "condition_faults_routing"
    assert item.field_path == "pipe.route_parcel"
    assert item.message == reason
    assert expression_text not in item.message


def _caller_payload(verdict: ValidateBundleError) -> dict[str, Any]:
    """What a caller reads of a verdict: its problem in the caller's view and its validation items."""
    return {
        "problem": verdict.to_problem(view=ProblemView.CALLER).to_wire(),
        "validation_errors": [item.model_dump(mode="json", exclude_none=True) for item in verdict.validation_error_items()],
    }


def _assert_the_caller_reads_one_item(*, verdict: ValidateBundleError, reason: str, expression_text: str) -> None:
    payload = _caller_payload(verdict)
    assert [item["message"] for item in payload["validation_errors"]] == [reason]
    problem = verdict.to_problem(view=ProblemView.CALLER)
    assert problem.code == CoreCode.METHOD_INVALID
    (problem_item,) = problem.errors or []
    # An item carries its own fault's code, never the verdict's umbrella, whose sentence says nothing of the condition.
    assert problem_item.code != CoreCode.METHOD_INVALID
    assert problem_item.location is not None
    assert problem_item.location.pipe == "route_parcel"
    assert expression_text not in json.dumps(payload)


@pytest.mark.asyncio(loop_scope="class")
class TestConditionExpressionParseRefusal:
    @_CASES
    async def test_validation_refuses_it_as_an_item_on_the_condition(self, bundle: str, reason: str, expression_text: str) -> None:
        """The verdict carries one item on the condition, the same in the validation items and in the caller's problem."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[bundle])
        verdict = exc_info.value

        (item,) = verdict.validation_error_items() or []
        _assert_is_the_refusal(item=item, reason=reason, expression_text=expression_text)

        _assert_the_caller_reads_one_item(verdict=verdict, reason=reason, expression_text=expression_text)

    @_CASES
    async def test_a_run_answers_422_with_the_item(self, bundle: str, reason: str, expression_text: str) -> None:
        """A run is refused with the verdict validation gives, before any pipe runs, and a hosted run answers 422 with its item."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await PipelexMTHDSProtocol().execute(
                pipe_code="route_parcel", mthds_contents=[bundle], inputs={"parcel": "a box of books", "lane": "express"}
            )
        verdict = exc_info.value

        (item,) = verdict.validation_error_items() or []
        _assert_is_the_refusal(item=item, reason=reason, expression_text=expression_text)

        _assert_the_caller_reads_one_item(verdict=verdict, reason=reason, expression_text=expression_text)
        assert error_code_spec(CoreCode.METHOD_INVALID).status == 422
        assert verdict.to_problem(view=ProblemView.CALLER).next_step.kind == StepKind.CHANGE_METHOD

    async def test_a_host_library_condition_puts_none_of_its_text_in_what_the_caller_reads(self, tmp_path: Path) -> None:
        """Beside a host's library directory, the refusal of its condition is the host's fault, naming neither its expression nor its file."""
        host_library_dir = tmp_path / "host" / "library"
        host_library_dir.mkdir(parents=True)
        (host_library_dir / "routing.mthds").write_text(ConditionExpressionParseTestData.UNKNOWN_TAG_TEMPLATE_MTHDS, encoding="utf-8")

        with pytest.raises(HostLibraryLoadRefusalError) as exc_info:
            await validate_bundle(mthds_contents=[ConditionExpressionParseTestData.VALID_CALLER_MTHDS], library_dirs=[host_library_dir])

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.errors is None
        serialized_payload = json.dumps(caller.to_wire())
        assert "frobnicate_the_parcel" not in serialized_payload
        assert "lane ==" not in serialized_payload
        assert str(tmp_path) not in serialized_payload
        assert str(tmp_path.resolve()) not in serialized_payload
