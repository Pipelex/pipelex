"""Pin: a `PipeCondition` whose expression does not parse is refused as an item of the bundle's verdict.

The expression is the method author's own, so the refusal is the caller's to fix: validation answers an invalid
verdict with one item on the condition, saying its expression does not parse and at which line, and a run of the
bundle answers with the same verdict, which a hosted run serves as HTTP 422. Before, the parser's own error
escaped the load, so validation gave no verdict and a hosted run answered 500 "An internal error occurred.".

The item quotes neither the expression nor the parser's diagnosis, which names the token it stopped at: the
verdict is kept verbatim under STRICT disclosure, and a condition declared in a host's library directories must
not put its text there.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from pipelex.base_exceptions import DisclosureMode, ValidationErrorCategory, ValidationErrorItem
from pipelex.pipeline.exceptions import ValidateBundleError
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

_EXPRESSION_REASON = (
    "Validation error at 'pipe.route_parcel': The 'expression' of this PipeCondition does not parse at line 1 of that expression. "
    "Fix it so that it parses as a Jinja2 expression."
)
_TEMPLATE_REASON = (
    "Validation error at 'pipe.route_parcel': The 'expression_template' of this PipeCondition does not parse at line 2 of that expression. "
    "Fix it so that it parses as a Jinja2 template."
)

_CASES = pytest.mark.parametrize(
    ("bundle", "reason", "expression_text"),
    [
        (_DANGLING_OPERATOR_BUNDLE, _EXPRESSION_REASON, "lane =="),
        (_TAG_INSIDE_EXPRESSION_BUNDLE, _EXPRESSION_REASON, "{% if %}"),
        (ConditionExpressionParseTestData.UNKNOWN_TAG_TEMPLATE_MTHDS, _TEMPLATE_REASON, "frobnicate_the_parcel"),
    ],
    ids=["dangling_operator", "tag_inside_expression", "unknown_tag_on_line_2"],
)


def _assert_is_the_refusal(*, item: ValidationErrorItem, reason: str, expression_text: str) -> None:
    assert item.category == ValidationErrorCategory.BLUEPRINT_VALIDATION
    assert item.pipe_code == "route_parcel"
    assert item.domain_code == "condition_faults_routing"
    assert item.field_path == "pipe.route_parcel"
    assert item.message == reason
    assert expression_text not in item.message


def _strict_item_messages(payload: dict[str, Any]) -> list[str]:
    return [item["message"] for item in payload["validation_errors"]]


@pytest.mark.asyncio(loop_scope="class")
class TestConditionExpressionParseRefusal:
    @_CASES
    async def test_validation_refuses_it_as_an_item_on_the_condition(self, bundle: str, reason: str, expression_text: str) -> None:
        """The verdict carries one item on the condition, the same locally and in the STRICT payload."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[bundle])
        verdict = exc_info.value

        (item,) = verdict.to_error_report().validation_errors or []
        _assert_is_the_refusal(item=item, reason=reason, expression_text=expression_text)

        strict_payload = verdict.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert _strict_item_messages(strict_payload) == [reason]
        assert expression_text not in json.dumps(strict_payload)

    @_CASES
    async def test_a_run_answers_422_with_the_item(self, bundle: str, reason: str, expression_text: str) -> None:
        """A run is refused with the verdict validation gives, before any pipe runs, and a hosted run answers 422 with its item."""
        with pytest.raises(ValidateBundleError) as exc_info:
            await PipelexMTHDSProtocol().execute(
                pipe_code="route_parcel", mthds_contents=[bundle], inputs={"parcel": "a box of books", "lane": "express"}
            )
        verdict = exc_info.value

        (item,) = verdict.to_error_report().validation_errors or []
        _assert_is_the_refusal(item=item, reason=reason, expression_text=expression_text)

        document = verdict.to_error_report().to_problem_document(disclosure_mode=DisclosureMode.STRICT)
        assert document["status"] == 422
        assert document["error_domain"] == "input"
        assert document["error_type"] == "ValidateBundleError"
        assert document["detail"] == reason
        assert _strict_item_messages(document) == [reason]
        assert document["user_action"]["kind"] == "change_input"
        assert expression_text not in json.dumps(document)

    async def test_a_host_library_condition_puts_none_of_its_text_in_the_strict_verdict(self, tmp_path: Path) -> None:
        """Beside a host's library directory, the refusal of its condition names neither its expression nor its file."""
        host_library_dir = tmp_path / "host" / "library"
        host_library_dir.mkdir(parents=True)
        (host_library_dir / "routing.mthds").write_text(ConditionExpressionParseTestData.UNKNOWN_TAG_TEMPLATE_MTHDS, encoding="utf-8")

        with pytest.raises(ValidateBundleError) as exc_info:
            await validate_bundle(mthds_contents=[ConditionExpressionParseTestData.VALID_CALLER_MTHDS], library_dirs=[host_library_dir])

        strict_payload = exc_info.value.to_error_report().to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert _strict_item_messages(strict_payload) == [_TEMPLATE_REASON]
        serialized_payload = json.dumps(strict_payload)
        assert "frobnicate_the_parcel" not in serialized_payload
        assert "lane ==" not in serialized_payload
        assert str(tmp_path) not in serialized_payload
        assert str(tmp_path.resolve()) not in serialized_payload
